def classify(value: object) -> str:
    match value:
        case int():
            return "integer"
        case _:
            return "other"
