from app.config import get_settings
from app.retrieval import PolicyIndex

if __name__ == '__main__':
    settings = get_settings()
    index = PolicyIndex(settings)
    index.export(settings.cache_dir / 'chunks.json')
    print(f'Indexed {len(index.chunks)} clauses from {settings.policy_path.name}')
    print('Policy SHA256:', index.policy_sha256)
    print('Search check:', [(r['pages'], r['section']) for r in index.search('30 days Waiting Period', 3)])
