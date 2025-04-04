import os
import requests

# Match the environment handling used in update_project_from_results.py
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_ORG = os.environ.get("GITHUB_ORG")
GITHUB_PROJECT_NUMBER = os.environ.get("GITHUB_PROJECT_NUMBER")

if GITHUB_PROJECT_NUMBER is not None:
    GITHUB_PROJECT_NUMBER = int(GITHUB_PROJECT_NUMBER)

GRAPHQL_URL = "https://api.github.com/graphql"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

def graphql(query, variables=None):
    response = requests.post(
        GRAPHQL_URL,
        headers=HEADERS,
        json={"query": query, "variables": variables or {}}
    )
    response.raise_for_status()
    return response.json()

def main():
    query = """
    query($org: String!, $number: Int!) {
      organization(login: $org) {
        projectV2(number: $number) {
          fields(first: 50) {
            nodes {
              __typename
              ... on ProjectV2SingleSelectField {
                id
                name
                options {
                  id
                  name
                }
              }
            }
          }
        }
      }
    }
    """
    variables = {"org": GITHUB_ORG, "number": GITHUB_PROJECT_NUMBER}
    data = graphql(query, variables)
    fields = data["data"]["organization"]["projectV2"]["fields"]["nodes"]

    print("Single-select field options:")
    for field in fields:
        if field["__typename"] == "ProjectV2SingleSelectField":
            print(f"\nField: {field['name']} (id: {field['id']})")
            for option in field["options"]:
                print(f"  - {option['name']} (option id: {option['id']})")

if __name__ == "__main__":
    main()

