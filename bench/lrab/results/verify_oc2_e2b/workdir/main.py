# Main application logic
import os
import json

def load_config(config_path="config.json"):
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {config_path}")
        return None

def load_skills(skills_dir="skills"):
    skills = {}
    if os.path.exists(skills_dir):
        for filename in os.listdir(skills_dir):
            if filename.endswith(".md"):
                name = filename[:-3]
                try:
                    with open(os.path.join(skills_dir, filename), 'r') as f:
                        content = f.read()
                        skills[name] = content
                except Exception as e:
                    print(f"Error reading skill file {filename}: {e}")
    return skills

def main():
    config = load_config()
    skills = load_skills()

    if config and skills:
        print("Configuration loaded successfully.")
        print(f"Loaded {len(skills)} skills.")
        # Example of using a skill (mock)
        if "setup" in skills:
            print("Setup skill loaded.")
        
        # In a real agent, this is where task execution would happen
    else:
        print("Failed to load configuration or skills. Exiting.")

if __name__ == "__main__":
    main()