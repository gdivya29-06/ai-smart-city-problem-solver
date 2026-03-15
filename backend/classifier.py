DEPARTMENT_MAP = {
    "pothole": "Road Maintenance",
    "road damage": "Road Maintenance",
    "crack": "Road Maintenance",
    "garbage": "Waste Management",
    "trash": "Waste Management",
    "litter": "Waste Management",
    "waste": "Waste Management",
    "streetlight": "Electricity Department",
    "street light": "Electricity Department",
    "lamp": "Electricity Department",
    "lighting": "Electricity Department",
    "broken light": "Electricity Department",
}


def classify_issue(detected_text: str) -> tuple[str, str]:
    detected_lower = detected_text.lower()
    for keyword, department in DEPARTMENT_MAP.items():
        if keyword in detected_lower:
            issue_label = keyword.replace(" ", "_")
            return issue_label, department
    return "unknown_issue", "General Maintenance"
