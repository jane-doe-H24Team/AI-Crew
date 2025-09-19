import math

def calculator(expression: str):
    """Evaluate a mathematical expression."""
    try:
        # A safe way to evaluate mathematical expressions
        allowed_names = {k: v for k, v in math.__dict__.items() if not k.startswith("__")}
        code = compile(expression, "<string>", "eval")
        for name in code.co_names:
            if name not in allowed_names:
                raise NameError(f"Use of {name} is not allowed")
        return eval(code, {"__builtins__": {}}, allowed_names)
    except Exception as e:
        return f"Error: {e}"

def get_tool_definition():
    return {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a mathematical expression using Python's math library.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to evaluate (e.g., '2*pi*5').",
                    }
                },
                "required": ["expression"],
            },
        }
    }
