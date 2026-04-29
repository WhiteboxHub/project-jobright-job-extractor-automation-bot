import json

path = r'c:\Users\Innovapath\Desktop\job_engine\jobright-engine\jobright_by_ats.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

new_data = {
    'source': data.get('source'),
    'categorized_by': 'ats_platform',
    'platforms': data.get('platforms'),
    'by_ats': {}
}

for ats, jobs in data.get('by_ats', {}).items():
    new_jobs = []
    for job in jobs:
        # Infer country if 'USA' or 'United States' or 'US' is in location
        loc = job.get('location') or ''
        country = None
        if 'United States' in loc or ' USA' in loc or loc.endswith(', US') or loc.endswith(', USA') or loc == 'United States':
            country = 'United States'
            
        new_job = {
            'job_id': job.get('job_id'),
            'title': job.get('title'),
            'jobright_url': job.get('jobright_url'),
            'ats_url': job.get('ats_url'),
            'job_tittle': job.get('title'),
            'comapany': job.get('company'),
            'location': job.get('location'),
            'city': job.get('city'),
            'state': job.get('state'),
            'country': country,
            'type': job.get('work_mode'),
            'company_description': None
        }
        new_jobs.append(new_job)
    new_data['by_ats'][ats] = new_jobs

with open(path, 'w', encoding='utf-8') as f:
    json.dump(new_data, f, indent=2)
