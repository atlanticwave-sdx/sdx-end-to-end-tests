import os
import xml.etree.ElementTree as ET
import requests
from datetime import datetime

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_ORG = os.environ.get("GITHUB_ORG")
GITHUB_PROJECT_NUMBER = int(os.environ.get("GITHUB_PROJECT_NUMBER", "0"))

GRAPHQL_URL = "https://api.github.com/graphql"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

SINGLE_SELECT_IDS = {
    "current": {
        "Pass": "844cbec9",
        "Fail": "c16ad980",
        "Skipped": "0bf63457",
        "Other": "31038a70"
    },
    "previous": {
        "Pass": "6beffb55",
        "Fail": "7b8a0aaa",
        "Skipped": "f2f334fd",
        "Other": "bc5a3854"
    }
}

def graphql(query, variables=None):
    response = requests.post(
        GRAPHQL_URL,
        headers=HEADERS,
        json={"query": query, "variables": variables or {}}
    )
    response.raise_for_status()
    data = response.json()
    if "errors" in data:
        for err in data["errors"]:
            print("GraphQL error:", err["message"])
        raise Exception("GraphQL query failed.")
    return data

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
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    name
                    field {
                      ... on ProjectV2FieldCommon {
                        id
                        name
                      }
                    }
                  }
                  ... on ProjectV2ItemFieldNumberValue {
                    number
                    field {
                        ... on ProjectV2FieldCommon {
                        id
                        name
                      }
                    }
                  }
                  ... on ProjectV2ItemFieldDateValue {
                    date
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
    return graphql(query, {"org": GITHUB_ORG, "number": GITHUB_PROJECT_NUMBER})

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
            "value": {"text": str(value)}
        }
    }
    graphql(mutation, variables)

def update_number_field(project_id, item_id, field_id, value):
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
            "value": {"number": value}
        }
    }
    graphql(mutation, variables)

def update_single_select(project_id, item_id, field_id, option_id):
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
            "value": {"singleSelectOptionId": option_id}
        }
    }
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
            message = (failure.attrib.get("message", "") + "\n" + (failure.text or "")).strip()
        elif skipped is not None:
            status = "Skipped"
            message = "Test was skipped."

        results.append({
            "name": name,
            "classname": classname,
            "time": time,
            "status": status,
            "message": message[:500]
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
    field_values_by_item = {}

    for item in items:
        item_fields = item.get("fieldValues", {}).get("nodes", [])
        test_name = None
        field_values = {}
        for field_value in item_fields:
            field = field_value.get("field", {})
            field_name = field.get("name")
            field_id = field.get("id")
            text = (
                field_value.get("text")
                or field_value.get("name")
                or field_value.get("number")  # This allows reading number fields
            )
            if field_name and field_id:
                field_ids[field_name] = field_id
                field_values[field_name] = text
                if field_name == "name":
                    test_name = text
        if test_name:
            item_map[test_name] = item
            field_values_by_item[item["id"]] = field_values

    print("\nAvailable project fields:")
    for name, fid in field_ids.items():
        print(f"  {name}: {fid}")

    results = parse_results("e2e-output/results.xml")
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    for result in results:
        name = result["name"]
        if name not in item_map:
            print(f"Skipping unmatched test: {name}")
            continue

        item = item_map[name]
        item_id = item["id"]
        status = result["status"]
        current_fields = field_values_by_item.get(item_id, {})
        old_status = current_fields.get("current", "Other")

        # Update select fields if changed
        if old_status != status:
            print(f"UPDATE: {name} | {old_status} → {status}")
            update_single_select(project_id, item_id, field_ids["previous"],
                                 SINGLE_SELECT_IDS["previous"].get(old_status, SINGLE_SELECT_IDS["previous"]["Other"]))
            update_single_select(project_id, item_id, field_ids["current"],
                                 SINGLE_SELECT_IDS["current"].get(status, SINGLE_SELECT_IDS["current"]["Other"]))

            if status == "Pass":
                update_project_field(project_id, item_id, field_ids.get("lastpass"), now)
                try:
                    count = int(current_fields.get("passes", 0)) + 1
                except:
                    count = 1
                update_number_field(project_id, item_id, field_ids.get("passes"), count)

            elif status == "Fail":
                update_project_field(project_id, item_id, field_ids.get("lastfail"), now)
                try:
                    count = int(current_fields.get("fails", 0)) + 1
                except:
                    count = 1
                update_number_field(project_id, item_id, field_ids.get("fails"), count)

        # Update reason field if changed
        output = (
            f"Status: {status}\n"
            f"File: {result['classname'].replace('.', '/')}.py\n"
            f"Name: {name}\n"
            f"Duration: {result['time']:.2f}s\n"
        )
        if result["message"]:
            output += f"\nMessage:\n{result['message']}"

        if current_fields.get("reason") != output:
            update_project_field(project_id, item_id, field_ids.get("reason"), output)

if __name__ == "__main__":
    main()

