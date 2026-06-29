import os
import json
import glob
import re

def extract_tests():
    brain_dir = r"C:\Users\egorribun\.gemini\antigravity\brain"
    output_dir = r"C:\Users\egorribun\Documents\university_ecosystem\recovered_tests"
    
    transcripts = glob.glob(os.path.join(brain_dir, "*", ".system_generated", "logs", "transcript_full.jsonl"))
    if not transcripts:
        transcripts = glob.glob(os.path.join(brain_dir, "*", ".system_generated", "logs", "transcript.jsonl"))

    print(f"Found {len(transcripts)} transcripts.")

    os.makedirs(output_dir, exist_ok=True)
    
    file_pattern = re.compile(r'([a-zA-Z0-9_/-]+\.(?:test\.tsx?|test\.ts|py|go))')
    code_block_pattern = re.compile(r'```(?:tsx?|go|python)?\s*\n(.*?)\n```', re.DOTALL)
    
    extracted_count = 0
    seen_code = set()
    
    for transcript in transcripts:
        try:
            with open(transcript, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        step = json.loads(line)
                        text = step.get('content', '')
                        if not text:
                            continue
                        
                        # Find all code blocks
                        blocks = code_block_pattern.finditer(text)
                        for block in blocks:
                            code = block.group(1).strip()
                            if not code or len(code) < 50:
                                continue
                            
                            # Deduplicate blocks since checkpoints repeat history
                            if code in seen_code:
                                continue
                            seen_code.add(code)
                            
                            start_idx = block.start()
                            
                            # Look backwards for a file name
                            preceding_text = text[max(0, start_idx-300):start_idx]
                            match = file_pattern.findall(preceding_text)
                            
                            if match:
                                filename = match[-1].strip('`/')
                                
                                # Fallbacks for exact paths
                                if filename.endswith('.test.tsx') or filename.endswith('.test.ts'):
                                    if not filename.startswith('frontend/'):
                                        filename = f"frontend/src/api/hooks/__tests__/{os.path.basename(filename)}"
                                elif filename.endswith('.go'):
                                    if not filename.startswith('services/'):
                                        filename = f"services/ws-hub/pkg/hub/{os.path.basename(filename)}"
                                elif filename.endswith('.py'):
                                    if not filename.startswith('tests/'):
                                        filename = f"tests/{os.path.basename(filename)}"
                                        
                                out_path = os.path.join(output_dir, filename.replace('/', os.sep))
                                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                                
                                # append mode just in case there are multiple chunks for same file
                                with open(out_path, 'a', encoding='utf-8') as out_f:
                                    out_f.write(code + "\n\n")
                                extracted_count += 1
                                print(f"Recovered: {filename}")
                            else:
                                # try to guess based on content
                                if 'renderHook' in code and 'useActivities' in code:
                                    filename = 'frontend/src/api/hooks/__tests__/activity.test.ts'
                                elif 'renderHook' in code and 'useAuditLogs' in code:
                                    filename = 'frontend/src/api/hooks/__tests__/adminAudit.test.ts'
                                elif 'testing' in code and 'go' in code:
                                    filename = 'services/ws-hub/pkg/hub/unknown_test.go'
                                else:
                                    filename = f'unknown_{extracted_count}.txt'
                                
                                out_path = os.path.join(output_dir, filename.replace('/', os.sep))
                                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                                with open(out_path, 'a', encoding='utf-8') as out_f:
                                    out_f.write(code + "\n\n")
                                extracted_count += 1
                                print(f"Recovered (guessed name): {filename}")

                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"Error reading {transcript}: {e}")
            
    print(f"Total files recovered: {extracted_count}")

if __name__ == "__main__":
    extract_tests()
