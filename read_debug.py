with open("fixture_debug.txt", "rb") as f:
    try:
        content = f.read().decode("utf-16le")
    except:
        content = f.read().decode("utf-8", errors="ignore")
    print(content)
