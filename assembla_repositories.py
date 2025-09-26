import os
import requests
from dotenv import load_dotenv
import json
import csv
from datetime import datetime

def load_spaces_from_csv(csv_filename="space_list.csv"):
    """
    Load space information from CSV file
    
    Returns list of space names
    """
    spaces = []
    try:
        with open(csv_filename, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                space_name = row['space_name'].strip()
                if space_name and space_name != 'My Project Space':  # Skip example entries
                    spaces.append(space_name)
        
        if not spaces:
            print(f"No valid spaces found in {csv_filename}")
            print("Please update the CSV file with your actual space names")
            
        return spaces
        
    except FileNotFoundError:
        print(f"Error: {csv_filename} not found.")
        print("Please create the file with column: space_name")
        return []
    except Exception as e:
        print(f"Error reading {csv_filename}: {e}")
        return []

def fetch_assembla_repositories_for_space(space_name):
    """
    Fetch repository metadata from Assembla API for a specific space
    
    Gets repository list with details like type, size, commits, branches, tags, and PRs
    """
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Get API credentials from environment variables
    api_key = os.getenv('x-api-key')
    api_secret = os.getenv('x-api-secret')
    
    if not all([api_key, api_secret]):
        print("Error: Missing required environment variables.")
        print("Please ensure .env file contains: x-api-key and x-api-secret")
        return None
    
    # Set up headers for API requests
    headers = {
        'X-Api-Key': api_key,
        'X-Api-Secret': api_secret,
        'Content-Type': 'application/json'
    }
    
    print(f"\nProcessing space: {space_name}")
    print("=" * 60)
    
    try:
        # First get repository details from repos endpoint (has size, last_commit_at)
        repos_url = f"https://in-api.assembla.com/v1/spaces/{space_name}/repos.json"
        print(f"Fetching repository details from: {repos_url}")
        
        repos_response = requests.get(repos_url, headers=headers)
        repos_response.raise_for_status()
        
        repos_data = repos_response.json()
        
        # Create a lookup dict by repo id
        repos_lookup = {repo['id']: repo for repo in repos_data}
        
        # Fetch space tools (repositories)
        space_tools_url = f"https://in-api.assembla.com/v1/spaces/{space_name}/space_tools.json"
        
        print(f"Fetching space tools from: {space_tools_url}")
        response = requests.get(space_tools_url, headers=headers)
        response.raise_for_status()
        
        space_tools = response.json()
        
        # Filter for repository tools and get detailed info
        repositories = []
        repo_types = ['GitTool', 'SubversionTool', 'PerforceDepotTool']
        
        for tool in space_tools:
            tool_type = tool.get('type')
            if tool_type in repo_types:
                tool_id = tool.get('id')
                
                # Get basic info from space_tools
                repo_info = {
                    'id': tool_id,
                    'name': tool.get('name'),
                    'menu_name': tool.get('menu_name'),  # This is the actual repo name
                    'type': tool_type,
                    'created_at': tool.get('created_at'),
                    'updated_at': tool.get('updated_at'),
                    'space_id': space_name,
                    'space_name': space_name
                }
                
                # Add detailed info from repos endpoint if available
                if tool_id in repos_lookup:
                    repo_data = repos_lookup[tool_id]
                    size_bytes = repo_data.get('size', 0)
                    size_mb = round(size_bytes / (1024 * 1024), 2) if size_bytes > 0 else 0
                    
                    repo_info.update({
                        'size': size_bytes,
                        'size_mb': size_mb,
                        'last_commit_at': repo_data.get('last_commit_at'),
                        'default_branch': repo_data.get('default_branch'),
                        'clone_url_https': repo_data.get('https_clone_url'),
                        'clone_url_ssh': repo_data.get('ssh_clone_url')
                    })
                    

                    # If repository has a last_commit_at, it likely has commits even if API can't detect them
                    if repo_data.get('last_commit_at'):
                        print(f"    Note: Repository {tool.get('menu_name')} has last_commit_at - contains data")
                        repo_info['is_likely_imported'] = True
                        repo_info['has_commits_indicator'] = True
                    else:
                        repo_info['is_likely_imported'] = False
                        repo_info['has_commits_indicator'] = False
                
                # Get additional statistics for Git repositories
                if tool_type == 'GitTool':
                    try:
                        # Pass repository data if available
                        repo_data_for_stats = repos_lookup.get(tool_id) if tool_id in repos_lookup else None
                        repo_stats = get_git_repo_statistics(headers, space_name, tool_id, repo_data_for_stats)
                        repo_info.update(repo_stats)
                    except Exception as e:
                        print(f"Warning: Could not fetch statistics for repo {tool.get('menu_name')}: {e}")
                
                repositories.append(repo_info)
        
        if not repositories:
            print("No repositories found in this space")
            return None
        
        # Display results
        print(f"\nFound {len(repositories)} repositories:")
        print("=" * 60)
        
        for i, repo in enumerate(repositories, 1):
            # Improved empty repository detection
            is_empty = (repo.get('commits_count', 0) == 0 and 
                       repo.get('branches_count', 0) == 0 and 
                       repo.get('size', 0) == 0 and
                       not repo.get('last_commit_at') and
                       not repo.get('has_commits_indicator', False))
            
            is_imported = repo.get('is_likely_imported', False)
            
            if is_empty:
                status_indicator = " [EMPTY REPOSITORY]"
            elif is_imported:
                status_indicator = " [IMPORTED REPOSITORY]"
            else:
                status_indicator = ""
            
            print(f"\nRepository #{i}{status_indicator}:")
            print(f"  Space: {repo.get('space_name', 'N/A')}")
            print(f"  ID: {repo.get('id', 'N/A')}")
            print(f"  Technical Name: {repo.get('name', 'N/A')}")
            print(f"  Repository Name: {repo.get('menu_name', 'N/A')}")
            print(f"  Type: {repo.get('type', 'N/A')}")
            print(f"  Created: {repo.get('created_at', 'N/A')}")
            size_display = f"{repo.get('size_mb', 0)} MB" if repo.get('size_mb', 0) > 0 else f"{repo.get('size', 0)} bytes"
            print(f"  Size: {size_display}")
            print(f"  Default Branch: {repo.get('default_branch', 'N/A')}")
            print(f"  Last Commit: {repo.get('last_commit_at', 'N/A')}")
            print(f"  Commits: {repo.get('commits_count', 'N/A')}")
            print(f"  Branches: {repo.get('branches_count', 'N/A')}")
            print(f"  Tags: {repo.get('tags_count', 'N/A')}")
            print(f"  Merge Requests: {repo.get('merge_requests_count', 'N/A')}")
            
            if is_empty:
                print(f"  Status: Empty repository - no code has been committed")
            elif is_imported:
                print(f"  Status: Imported repository - contains data but API has limited access")
            
            if repo.get('last_commit_author'):
                print(f"  Last Author: {repo.get('last_commit_author', 'N/A')}")
            if repo.get('last_commit_message'):
                message = repo.get('last_commit_message', '')[:100] + '...' if len(repo.get('last_commit_message', '')) > 100 else repo.get('last_commit_message', '')
                print(f"  Last Message: {message}")
        
        return repositories
        
    except requests.exceptions.RequestException as e:
        print(f"API request error: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None

def get_git_repo_statistics(headers, space_id, repo_id, repo_data=None):
    """
    Get detailed statistics for Git repositories including commits, branches, tags, and PRs
    Fetches commits from all branches, not just the default branch
    """
    stats = {
        'commits_count': 0,
        'branches_count': 0,
        'tags_count': 0,
        'merge_requests_count': 0,
        'last_commit_author': '',
        'last_commit_message': '',
        'last_commit_at': ''
    }
    
    branches_list = []
    
    try:
        # Get branches list first - use the URL from repository data if available
        if repo_data and repo_data.get('branches_url'):
            branches_url = repo_data['branches_url'].replace('www.assembla.com/v1', 'in-api.assembla.com/v1')
            print(f"    Using repository-specific branches URL: {branches_url}")
        else:
            branches_url = f"https://in-api.assembla.com/v1/spaces/{space_id}/repos/git/branches"
            print(f"    Using default branches URL: {branches_url}")
            
        response = requests.get(branches_url, headers=headers)
        
        if response.status_code == 200:
            branches_list = response.json()
            stats['branches_count'] = len(branches_list)
            print(f"    Found {len(branches_list)} branches")
        elif response.status_code == 204:
            print(f"    No branches found (204), trying alternative approaches...")
            stats['branches_count'] = 0
            
            # Try multiple alternative endpoints for imported repositories
            alternative_endpoints = [
                f"https://in-api.assembla.com/v1/spaces/{space_id}/space_tools/{repo_id}/git/branches",
                f"https://in-api.assembla.com/v1/spaces/{space_id}/repos/{repo_id}/git/branches",
                f"https://in-api.assembla.com/v1/spaces/{space_id}/git_repos/{repo_id}/branches"
            ]
            
            for i, alt_url in enumerate(alternative_endpoints, 1):
                try:
                    print(f"    Trying alternative endpoint {i}: {alt_url}")
                    alt_response = requests.get(alt_url, headers=headers)
                    print(f"    Alternative endpoint {i} status: {alt_response.status_code}")
                    
                    if alt_response.status_code == 200:
                        branches_list = alt_response.json()
                        stats['branches_count'] = len(branches_list)
                        print(f"    SUCCESS: Found {len(branches_list)} branches using alternative endpoint {i}")
                        break
                    elif alt_response.status_code == 204:
                        print(f"    Alternative endpoint {i} also returned 204 (No Content)")
                    else:
                        print(f"    Alternative endpoint {i} failed with status {alt_response.status_code}")
                        
                except Exception as alt_e:
                    print(f"    Alternative endpoint {i} exception: {alt_e}")
        else:
            print(f"    Could not fetch branches, status: {response.status_code}")
            print(f"    Response: {response.text[:200] if response.text else 'No response text'}")
    except Exception as e:
        print(f"    Could not fetch branches: {e}")
    
    try:
        # Get tags count
        tags_url = f"https://in-api.assembla.com/v1/spaces/{space_id}/repos/git/tags"
        response = requests.get(tags_url, headers=headers)
        if response.status_code == 200:
            tags = response.json()
            stats['tags_count'] = len(tags)
        elif response.status_code == 204:  # No content means no tags
            stats['tags_count'] = 0
    except Exception as e:
        print(f"    Could not fetch tags: {e}")
    
    # Collect all commits from all branches
    all_commits = []
    latest_commit = None
    latest_commit_date = None
    
    if branches_list:
        for branch in branches_list:
            branch_name = branch.get('name', branch.get('id', 'unknown'))
            try:
                # Get commits for this specific branch - use repository-specific URL if available
                if repo_data and repo_data.get('commits_url'):
                    commits_url = repo_data['commits_url'].replace('www.assembla.com/v1', 'in-api.assembla.com/v1')
                else:
                    commits_url = f"https://in-api.assembla.com/v1/spaces/{space_id}/repos/git/commits"
                    
                params = {'branch': branch_name} if branch_name != 'unknown' else {}
                
                print(f"    Fetching commits from branch: {branch_name}")
                response = requests.get(commits_url, headers=headers, params=params)
                
                if response.status_code == 200:
                    branch_commits = response.json()
                    print(f"    Found {len(branch_commits)} commits in branch {branch_name}")
                    
                    # Add commits to our collection (avoid duplicates by commit ID)
                    for commit in branch_commits:
                        commit_id = commit.get('id', commit.get('sha', commit.get('revision', '')))
                        # If no unique ID found, use a combination of message and timestamp
                        if not commit_id:
                            commit_id = f"{commit.get('message', '')[:50]}_{commit.get('authored_at', commit.get('committed_at', ''))}"
                        
                        # Check for duplicates
                        is_duplicate = False
                        for existing_commit in all_commits:
                            existing_id = existing_commit.get('id', existing_commit.get('sha', existing_commit.get('revision', '')))
                            if not existing_id:
                                existing_id = f"{existing_commit.get('message', '')[:50]}_{existing_commit.get('authored_at', existing_commit.get('committed_at', ''))}"
                            
                            if commit_id == existing_id:
                                is_duplicate = True
                                break
                        
                        if not is_duplicate:
                            all_commits.append(commit)
                            
                            # Track the latest commit across all branches
                            commit_date = commit.get('authored_at', commit.get('committed_at', commit.get('date', '')))
                            if commit_date and (not latest_commit_date or commit_date > latest_commit_date):
                                latest_commit = commit
                                latest_commit_date = commit_date
                                
                else:
                    print(f"    Could not fetch commits for branch {branch_name}, status: {response.status_code}")
                    
            except Exception as e:
                print(f"    Could not fetch commits for branch {branch_name}: {e}")
    else:
        # Fallback: try to get commits without specifying branch
        try:
            # Use repository-specific commits URL if available
            if repo_data and repo_data.get('commits_url'):
                commits_url = repo_data['commits_url'].replace('www.assembla.com/v1', 'in-api.assembla.com/v1')
                print(f"    Using repository-specific commits URL: {commits_url}")
            else:
                commits_url = f"https://in-api.assembla.com/v1/spaces/{space_id}/repos/git/commits"
                print(f"    Using default commits URL: {commits_url}")
                
            response = requests.get(commits_url, headers=headers)
            if response.status_code == 200:
                all_commits = response.json()
                print(f"    Found {len(all_commits)} commits total")
                if all_commits:
                    latest_commit = all_commits[0]  # Assume first is latest
            elif response.status_code == 422:
                print(f"    No commits found (422), trying alternative approaches for imported repo...")
                
                # Try multiple alternative endpoints for imported repositories
                alternative_commit_endpoints = [
                    f"https://in-api.assembla.com/v1/spaces/{space_id}/space_tools/{repo_id}/git/commits",
                    f"https://in-api.assembla.com/v1/spaces/{space_id}/repos/{repo_id}/git/commits",
                    f"https://in-api.assembla.com/v1/spaces/{space_id}/git_repos/{repo_id}/commits"
                ]
                
                for i, alt_url in enumerate(alternative_commit_endpoints, 1):
                    try:
                        print(f"    Trying alternative commits endpoint {i}: {alt_url}")
                        alt_response = requests.get(alt_url, headers=headers)
                        print(f"    Alternative commits endpoint {i} status: {alt_response.status_code}")
                        
                        if alt_response.status_code == 200:
                            all_commits = alt_response.json()
                            print(f"    SUCCESS: Found {len(all_commits)} commits using alternative endpoint {i}")
                            if all_commits:
                                latest_commit = all_commits[0]
                            break
                        elif alt_response.status_code == 204:
                            print(f"    Alternative commits endpoint {i} returned 204 (No Content)")
                        else:
                            print(f"    Alternative commits endpoint {i} failed with status {alt_response.status_code}")
                            
                    except Exception as alt_e:
                        print(f"    Alternative commits endpoint {i} exception: {alt_e}")
                        
            elif response.status_code == 204:
                print(f"    Repository has no commits (204 No Content)")
            else:
                print(f"    Could not fetch commits, status: {response.status_code}")
                print(f"    Response: {response.text[:200] if response.text else 'No response text'}")
        except Exception as e:
            print(f"    Could not fetch commits: {e}")
    
    # Set final statistics
    stats['commits_count'] = len(all_commits)
    
    # If we found commits through API, use that data
    if latest_commit:
        author_info = latest_commit.get('author', {})
        if isinstance(author_info, dict):
            stats['last_commit_author'] = author_info.get('name', author_info.get('login', ''))
        else:
            stats['last_commit_author'] = str(author_info)
            
        stats['last_commit_message'] = latest_commit.get('message', '').replace('\n', ' ').replace('\r', ' ')
        stats['last_commit_at'] = latest_commit.get('authored_at', latest_commit.get('committed_at', ''))
    
    # If API failed but repository data indicates commits exist, estimate commit count
    elif repo_data and repo_data.get('last_commit_at') and stats['commits_count'] == 0:
        print(f"    API failed to get commits, but repository has last_commit_at - estimating commits exist")
        stats['last_commit_at'] = repo_data.get('last_commit_at')
        # For imported repos with branches but no detectable commits, estimate at least 1 commit per branch
        if stats['branches_count'] > 0:
            stats['commits_count'] = max(1, stats['branches_count'])  # At least 1 commit, or 1 per branch
            print(f"    Estimated {stats['commits_count']} commits based on {stats['branches_count']} branches")
        else:
            stats['commits_count'] = 1  # At least 1 commit if last_commit_at exists
            print(f"    Estimated 1 commit based on last_commit_at presence")
    
    try:
        # Get merge requests count
        mr_url = f"https://in-api.assembla.com/v1/spaces/{space_id}/space_tools/{repo_id}/merge_requests.json"
        response = requests.get(mr_url, headers=headers)
        if response.status_code == 200:
            merge_requests = response.json()
            stats['merge_requests_count'] = len(merge_requests)
    except Exception as e:
        print(f"    Could not fetch merge requests: {e}")
    
    print(f"    Final stats: {stats['commits_count']} commits, {stats['branches_count']} branches, {stats['tags_count']} tags, {stats['merge_requests_count']} MRs")
    return stats

def save_repositories_to_csv(repositories, filename):
    """Save repositories data to CSV file"""
    if not repositories:
        return
    
    # Define CSV headers
    headers = [
        'Space_Name', 'ID', 'Technical_Name', 'Repository_Name', 'Type', 'Created_At', 'Updated_At',
        'Size_Bytes', 'Size_MB', 'Default_Branch', 'Last_Commit_At', 'Commits_Count', 
        'Branches_Count', 'Tags_Count', 'Merge_Requests_Count', 'Is_Empty',
        'Last_Commit_Author', 'Last_Commit_Message', 'HTTPS_Clone_URL', 'SSH_Clone_URL'
    ]
    
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write headers
            writer.writerow(headers)
            
            # Write data rows
            for repo in repositories:
                # Improved empty repository detection
                is_empty = (repo.get('commits_count', 0) == 0 and 
                           repo.get('branches_count', 0) == 0 and 
                           repo.get('size', 0) == 0 and
                           not repo.get('last_commit_at') and
                           not repo.get('has_commits_indicator', False))
                
                is_imported = repo.get('is_likely_imported', False)
                
                row = [
                    repo.get('space_name', ''),
                    repo.get('id', ''),
                    repo.get('name', ''),  # Technical name (like git, git-2)
                    repo.get('menu_name', ''),  # Actual repository name (like test-repo, Address-book)
                    repo.get('type', ''),
                    repo.get('created_at', ''),
                    repo.get('updated_at', ''),
                    repo.get('size', ''),
                    repo.get('size_mb', ''),
                    repo.get('default_branch', ''),
                    repo.get('last_commit_at', ''),
                    repo.get('commits_count', ''),
                    repo.get('branches_count', ''),
                    repo.get('tags_count', ''),
                    repo.get('merge_requests_count', ''),
                    'True' if is_empty else ('Imported' if is_imported else 'False'),
                    repo.get('last_commit_author', ''),
                    repo.get('last_commit_message', ''),
                    repo.get('clone_url_https', ''),
                    repo.get('clone_url_ssh', '')
                ]
                writer.writerow(row)
                
        print(f"CSV file saved successfully with {len(repositories)} records")
        
    except Exception as e:
        print(f"Error saving CSV file: {e}")

def fetch_all_repositories():
    """
    Fetch repositories from all spaces defined in CSV file
    """
    # Load spaces from CSV
    spaces = load_spaces_from_csv()
    
    if not spaces:
        return None
    
    all_repositories = []
    
    for space_name in spaces:
        print(f"\nFetching repositories for space: {space_name}")
        repositories = fetch_assembla_repositories_for_space(space_name)
        
        if repositories:
            all_repositories.extend(repositories)
            print(f"Found {len(repositories)} repositories in {space_name}")
        else:
            print(f"No repositories found or error occurred for space: {space_name}")
    
    return all_repositories

def main():
    """Main function to run the script"""
    print("Assembla Repositories Metadata Fetcher (Multiple Spaces)")
    print("=" * 60)
    
    all_repositories = fetch_all_repositories()
    
    if all_repositories:
        print(f"\n" + "=" * 60)
        print(f"SUMMARY: Successfully fetched {len(all_repositories)} repositories from all spaces!")
        
        # Group by space for summary
        spaces_summary = {}
        for repo in all_repositories:
            space_name = repo.get('space_name', 'Unknown')
            if space_name not in spaces_summary:
                spaces_summary[space_name] = 0
            spaces_summary[space_name] += 1
        
        print("\nRepositories per space:")
        for space_name, count in spaces_summary.items():
            print(f"  {space_name}: {count} repositories")
        
        # Automatically save to CSV file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"assembla_repositories_{timestamp}.csv"
        save_repositories_to_csv(all_repositories, csv_filename)
        print(f"\nResults saved to {csv_filename}")
    else:
        print("Failed to fetch repositories. Please check your configuration and try again.")
        print("Make sure:")
        print("1. space_list.csv exists with valid space IDs")
        print("2. .env file contains valid x-api-key and x-api-secret")

if __name__ == "__main__":
    main()
