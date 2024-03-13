def read_secrets(filename="secrets.txt"):
    secrets = {}
    with open(filename, "r") as file:
        for line in file:
            key, value = line.strip().split("=", 1)
            secrets[key] = value
    return secrets
