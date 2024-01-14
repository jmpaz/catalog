class Processor:
    def __init__(self, file_path):
        self.file_path = file_path
        self.content = []

    def read_file(self):
        """
        Reads an LRC file and stores its content in a list.
        Each element of the list is a tuple (timestamp, text).
        """
        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                for line in file:
                    if line.strip():
                        parts = line.strip().split("]  ")
                        if len(parts) == 2:
                            timestamp, text = parts
                            self.content.append((timestamp + "]", text))
        except FileNotFoundError:
            print(f"File not found: {self.file_path}")
        except IOError as e:
            print(f"Error reading file {self.file_path}: {e}")

    def extract_lines(self):
        """
        Extracts and returns the text from the LRC content as a list.
        """
        return [text for _, text in self.content]

    def extract_timestamps(self):
        """
        Extracts and returns only the timestamp part from the LRC content.
        """
        return [timestamp for timestamp, _ in self.content]

    def extract_text(self):
        """
        Returns the text from the LRC content as a single string.
        """
        extracted_lines = self.extract_lines()
        return " ".join(extracted_lines)

    # Placeholder for additional methods to perform operations on the content
    def perform_operations(self, operations):
        """
        Executes a series of operations on the content and returns their outputs.
        """
        results = []
        for operation in operations:
            result = globals()[operation](self.content)
            results.append(result)
        return "\n".join(results)

