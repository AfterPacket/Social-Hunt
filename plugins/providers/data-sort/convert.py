import json
import yaml

def convert_json_to_yaml_format(input_json_file, output_yaml_file):
    with open(input_json_file, 'r') as f:
        raw_data = json.load(f)
    
    # 1. Handle Input Format
    # Check if data is wrapped (e.g., inside "wmn-data.txt")
    data_content = raw_data
    if isinstance(raw_data, dict) and 'sites' not in raw_data:
        for v in raw_data.values():
            if isinstance(v, dict) and 'sites' in v:
                data_content = v
                break

    # 2. Build the Comment Header Manually
    # This creates the format: #  KeyName -> #     Value
    header_comments = []

    # Process License
    if 'license' in data_content:
        header_comments.append("#  license")
        for line in data_content['license']:
            # Remove quotes if they are in the string itself, or just print clean text
            header_comments.append(f"#     {line}")

    # Process Authors
    if 'authors' in data_content:
        header_comments.append("#  authors")
        for author in data_content['authors']:
            header_comments.append(f"#     {author}")

    # Process Categories
    if 'categories' in data_content:
        header_comments.append("#  categories")
        for cat in data_content['categories']:
            header_comments.append(f"#     {cat}")

    # 3. Process Sites for YAML
    yaml_data = {}
    
    for site in data_content.get('sites', []):
        site_name = site.get('name', '').lower().strip()
        
        if not site_name:
            continue
        
        e_code = site.get('e_code', 200)
        m_code = site.get('m_code', 404)
        
        success_patterns = []
        if e_code:
            success_patterns.append(str(e_code))
        e_string = site.get('e_string', '')
        if e_string:
            success_patterns.append(e_string)
        
        error_patterns = []
        if m_code:
            error_patterns.append(str(m_code))
        m_string = site.get('m_string', '')
        if m_string:
            error_patterns.append(m_string)
        
        yaml_data[site_name] = {
            'url': site.get('uri_check', '').replace('{account}', '{username}'),
            'timeout': 20,
            'ua_profile': f"{site_name}_android",
            'success_patterns': success_patterns,
            'error_patterns': error_patterns
        }
    
    # 4. Write Output
    with open(output_yaml_file, 'w') as f:
        # Write the clean, formatted comments
        f.write("\n".join(header_comments))
        f.write("\n\n") # Extra spacing before YAML
        
        # Write YAML data
        yaml.dump(yaml_data, f, 
                 default_flow_style=False, 
                 sort_keys=False, 
                 indent=2,
                 allow_unicode=True,
                 explicit_start=False)
    
    print(f"✅ Converted {len(yaml_data)} sites to {output_yaml_file}")
    return yaml_data

# Usage
if __name__ == "__main__":
    convert_json_to_yaml_format('wmn-data.json', 'output.yaml')