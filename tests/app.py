def process_user_data(data: str):
    # Example logic that might crash on certain inputs
    if "CRASH" in data:
        raise ValueError("Simulated crash!")
    return True
