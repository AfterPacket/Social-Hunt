import yaml
import re

def analyze_and_sort_yaml(input_yaml_file):
    """
    Load the YAML file, analyze URI patterns, and sort by type
    """
    with open(input_yaml_file, 'r') as f:
        # Read the entire file
        content = f.read()
        
        # Skip comment lines for parsing YAML
        yaml_content = ""
        for line in content.split('\n'):
            if not line.startswith('#'):
                yaml_content += line + '\n'
    
    # Parse the YAML content
    data = yaml.safe_load(yaml_content) or {}
    
    # Categorize domains
    search_domains = []
    user_domains = []
    other_domains = []
    
    for site_name, site_info in data.items():
        url = site_info.get('url', '')
        
        # Check for search pattern (typically contains 'q=', 'search=', etc.)
        search_patterns = [
            r'q=\{username\}',
            r'search=\{username\}',
            r'query=\{username\}',
            r'term=\{username\}',
            r'keywords=\{username\}',
            r'p=\{username\}'
        ]
        
        is_search = any(re.search(pattern, url, re.IGNORECASE) for pattern in search_patterns)
        
        # Check for user/profile pattern
        user_patterns = [
            r'\{username\}',  # Simple username replacement
            r'user/\{username\}',
            r'users/\{username\}',
            r'profile/\{username\}',
            r'profiles/\{username\}',
            r'u/\{username\}',
            r'@\{username\}'
        ]
        
        is_user = any(re.search(pattern, url, re.IGNORECASE) for pattern in user_patterns)
        
        # Determine category
        domain_info = {
            'name': site_name,
            'url': url,
            'info': site_info
        }
        
        if is_search:
            # Extract search parameter for additional info
            search_param = None
            for pattern in search_patterns:
                match = re.search(pattern, url, re.IGNORECASE)
                if match:
                    search_param = pattern.replace(r'\{username\}', '').replace('\\', '')
                    break
            
            domain_info['search_param'] = search_param
            search_domains.append(domain_info)
        elif is_user:
            user_domains.append(domain_info)
        else:
            other_domains.append(domain_info)
    
    # Sort each category alphabetically by domain name
    search_domains.sort(key=lambda x: x['name'])
    user_domains.sort(key=lambda x: x['name'])
    other_domains.sort(key=lambda x: x['name'])
    
    return {
        'search': search_domains,
        'user': user_domains,
        'other': other_domains
    }

def print_sorted_domains(sorted_data, output_format='text'):
    """
    Print the sorted domains in the specified format
    """
    if output_format == 'text':
        print("\n" + "="*80)
        print("SEARCH-BASED DOMAINS (q=, search=, etc.)")
        print("="*80)
        for domain in sorted_data['search']:
            print(f"• {domain['name']}: {domain['url']}")
            if 'search_param' in domain:
                print(f"  Search parameter: {domain['search_param']}")
        
        print("\n" + "="*80)
        print("USER/PROFILE-BASED DOMAINS ({username} in path)")
        print("="*80)
        for domain in sorted_data['user']:
            print(f"• {domain['name']}: {domain['url']}")
        
        print("\n" + "="*80)
        print("OTHER DOMAINS")
        print("="*80)
        for domain in sorted_data['other']:
            print(f"• {domain['name']}: {domain['url']}")
        
        # Print summary
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        print(f"Total domains: {len(sorted_data['search']) + len(sorted_data['user']) + len(sorted_data['other'])}")
        print(f"Search-based: {len(sorted_data['search'])}")
        print(f"User-based: {len(sorted_data['user'])}")
        print(f"Other: {len(sorted_data['other'])}")
    
    elif output_format == 'yaml':
        # Create organized YAML output
        output_data = {
            'search_domains': {d['name']: d['info'] for d in sorted_data['search']},
            'user_domains': {d['name']: d['info'] for d in sorted_data['user']},
            'other_domains': {d['name']: d['info'] for d in sorted_data['other']}
        }
        
        print(yaml.dump(output_data, 
                       default_flow_style=False, 
                       sort_keys=False, 
                       indent=2,
                       allow_unicode=True))

def save_sorted_yaml(sorted_data, output_file):
    """
    Save the sorted domains to a new YAML file
    """
    output_data = {
        'search_domains': {d['name']: d['info'] for d in sorted_data['search']},
        'user_domains': {d['name']: d['info'] for d in sorted_data['user']},
        'other_domains': {d['name']: d['info'] for d in sorted_data['other']}
    }
    
    with open(output_file, 'w') as f:
        yaml.dump(output_data, f,
                 default_flow_style=False,
                 sort_keys=False,
                 indent=2,
                 allow_unicode=True)
    
    print(f"✅ Sorted YAML saved to {output_file}")

def export_to_csv(sorted_data, output_file):
    """
    Export sorted domains to CSV for easy analysis
    """
    import csv
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Type', 'Domain Name', 'URL', 'Success Patterns', 'Error Patterns'])
        
        for domain in sorted_data['search']:
            writer.writerow([
                'Search',
                domain['name'],
                domain['url'],
                ', '.join(domain['info'].get('success_patterns', [])),
                ', '.join(domain['info'].get('error_patterns', []))
            ])
        
        for domain in sorted_data['user']:
            writer.writerow([
                'User',
                domain['name'],
                domain['url'],
                ', '.join(domain['info'].get('success_patterns', [])),
                ', '.join(domain['info'].get('error_patterns', []))
            ])
        
        for domain in sorted_data['other']:
            writer.writerow([
                'Other',
                domain['name'],
                domain['url'],
                ', '.join(domain['info'].get('success_patterns', [])),
                ', '.join(domain['info'].get('error_patterns', []))
            ])
    
    print(f"✅ CSV export saved to {output_file}")

# Main execution
if __name__ == "__main__":
    input_file = "output.yaml"
    
    # Analyze and sort the domains
    sorted_domains = analyze_and_sort_yaml(input_file)
    
    # Print results in text format
    print_sorted_domains(sorted_domains, output_format='text')
    
    # Save sorted YAML
    save_sorted_yaml(sorted_domains, "sorted_output.yaml")
    
    # Export to CSV (optional)
    export_to_csv(sorted_domains, "sorted_domains.csv")
    
    # Show examples of each type
    print("\n" + "="*80)
    print("EXAMPLES")
    print("="*80)
    
    if sorted_domains['search']:
        example = sorted_domains['search'][0]
        print(f"Search Example: {example['name']}")
        print(f"  URL: {example['url']}")
    
    if sorted_domains['user']:
        example = sorted_domains['user'][0]
        print(f"User Example: {example['name']}")
        print(f"  URL: {example['url']}")