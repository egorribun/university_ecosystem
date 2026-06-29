import os
import json
import glob

def recover_from_tools():
    brain_dir = r"C:\Users\egorribun\.gemini\antigravity\brain"
    output_dir = r"C:\Users\egorribun\Documents\university_ecosystem\recovered_tests_toolcalls"
    
    transcripts = glob.glob(os.path.join(brain_dir, "*", ".system_generated", "logs", "transcript_full.jsonl"))
    if not transcripts:
        transcripts = glob.glob(os.path.join(brain_dir, "*", ".system_generated", "logs", "transcript.jsonl"))

    print(f"Found {len(transcripts)} transcripts.")
    os.makedirs(output_dir, exist_ok=True)
    
    recovered_files = {}

    for transcript in transcripts:
        try:
            with open(transcript, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        step = json.loads(line)
                        if "tool_calls" in step:
                            for call in step["tool_calls"]:
                                if call.get("name") == "write_to_file":
                                    args = call.get("args", {})
                                    target_file = args.get("TargetFile", "")
                                    code = args.get("CodeContent", "")
                                    if target_file and code:
                                        # Normalize path to relative
                                        if "university_ecosystem" in target_file:
                                            rel_path = target_file.split("university_ecosystem")[-1].lstrip("\\/")
                                        else:
                                            rel_path = os.path.basename(target_file)
                                        
                                        # Keep track of the LAST write_to_file for each path
                                        recovered_files[rel_path] = code
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"Error reading {transcript}: {e}")

    for rel_path, code in recovered_files.items():
        out_path = os.path.join(output_dir, rel_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as out_f:
            out_f.write(code)
        print(f"Recovered from tool call: {rel_path}")

if __name__ == "__main__":
    recover_from_tools()
