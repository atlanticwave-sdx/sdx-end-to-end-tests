import os
import xml.etree.ElementTree as ET
import requests

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
ORG = os.environ["GITHUB_ORG"]
PROJECT_NUMBER = int(os.environ["GITHUB_PROJECT_NUMBER"])

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}
GRAPHQL_URL = "https://api.github.com/graphql"

def graphql(query, variables={}):
    response = requests.post(GRAPHQL_URL, headers=HEADERS, json={"query": query, "variables": variables})
    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        print("HTTP error:", e)
        print("Response content:", response.text)
        raise

    json_data = response.json()
    if "errors" in json_data:
        print("GraphQL errors:")
        for err in json_data["errors"]:
            print("-", err["message"])
        raise Exception("GraphQL query failed.")

    return json_data

def get_project_info_and_items():
    query = """
    query($org: String!, $number: Int!) {
      organization(login: $org) {
        projectV2(number: $number) {
          id
          items(first: 100) {
            nodes {
              id
              fieldValues(first: 50) {
                nodes {
                  ... on ProjectV2ItemFieldTextValue {
                    text
                    field {
                      ... on ProjectV2FieldCommon {
                        id
                        name
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    return graphql(query, {"org": ORG, "number": PROJECT_NUMBER})

def update_project_field(project_id, item_id, field_id, value):
    mutation = """
    mutation($input: UpdateProjectV2ItemFieldValueInput!) {
      updateProjectV2ItemFieldValue(input: $input) {
        projectV2Item {
          id
        }
      }
    }
    """
    variables = {
        "input": {
            "projectId": project_id,
            "itemId": item_id,
            "fieldId": field_id,
            "value": {"text": value}
        }
    }
    print(f"Updating field {field_id} on item {item_id} to: {value}")
    graphql(mutation, variables)

def parse_results(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()
    results = []

    for testcase in root.iter("testcase"):
        name = testcase.attrib.get("name")
        classname = testcase.attrib.get("classname")
        time = float(testcase.attrib.get("time", 0))
        status = "Pass"
        message = ""

        failure = testcase.find("failure")
        skipped = testcase.find("skipped")

        if failure is not None:
            status = "Fail"
            message = failure.attrib.get("message", "").strip()
        elif skipped is not None:
            status = "Skipped"
            message = "Test was skipped."

        results.append({
            "name": name,
            "classname": classname,
            "time": time,
            "status": status,
            "message": message[:500]  # truncate for display
        })

    return results

def main():
    data = get_project_info_and_items()
    project_data = data["data"]["organization"]["projectV2"]
    project_id = project_data["id"]
    print("Resolved project ID:", project_id)

    items = project_data["items"]["nodes"]
    item_map = {}
    field_ids = {}

    for item in items:
        item_fields = item.get("fieldValues", {}).get("nodes", [])
        test_name = None
        for field_value in item_fields:
            field = field_value.get("field", {})
            field_name = field.get("name")
            field_id = field.get("id")
            if field_name and field_id:
                field_ids[field_name] = field_id
                if field_name == "Test":
                    test_name = field_value.get("text")
        if test_name:
            item_map[test_name] = item

    print("Discovered fields:")
    for name, fid in field_ids.items():
        print(f"- {name}: {fid}")

    print("Available test names from 'Test' field:")
    for title in item_map.keys():
        print("-", title)

    results = parse_results("e2e-output/results.xml")

    for result in results:
        title = result["name"]
        if title not in item_map:
            print(f"Skipping unmatched test: {title}")
            continue

        item = item_map[title]
        item_id = item["id"]
        status = result["status"]

        if "last" not in field_ids:
            print("Field 'last' not found — skipping status update.")
        else:
            print(f"Updating status for {title} to {status}")
            update_project_field(project_id, item_id, field_ids["last"], status)

        if "output" not in field_ids:
            print("Field 'output' not found — skipping output update.")
        else:
            output = (
                f"Status: {status}\n"
                f"File: {result['classname'].replace('.', '/')}.py\n"
                f"Test: {title}\n"
                f"Duration: {result['time']:.2f}s\n"
            )
            if result["message"]:
                output += f"\nMessage:\n{result['message']}"

            print(f"Updating output for {title}")
            update_project_field(project_id, item_id, field_ids["output"], output)

if __name__ == "__main__":
    main()

