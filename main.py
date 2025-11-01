# ============================================
# ARQUIVO 1: main.py (salve na pasta python-api/)
# ============================================

"""
Academic Research Bot API - 100% FREE
Salve este arquivo como: python-api/main.py
"""

import asyncio
import aiohttp
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from datetime import datetime
import hashlib
import json
import os
from scholarly import scholarly
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Configuração do Redis (opcional - funciona sem)
try:
    import redis
    redis_url = os.getenv('REDIS_URL', None)
    if redis_url:
        redis_client = redis.from_url(redis_url, decode_responses=True)
        print("✅ Redis conectado!")
    else:
        redis_client = None
        print("⚠️  Redis não configurado (cache desabilitado)")
except ImportError:
    redis_client = None
    print("⚠️  Redis não instalado (cache desabilitado)")

app = FastAPI(
    title="Academic Research Bot - Free Edition",
    description="Busca artigos científicos em 6+ fontes gratuitas",
    version="1.0.0"
)

# ==========================================
# FUNÇÕES DE BUSCA
# ==========================================

def search_google_scholar(query: str, num_results: int = 10) -> List[Dict]:
    """Busca no Google Scholar via Scholarly"""
    results = []
    print(f"🔍 Buscando no Google Scholar: {query}")
    
    try:
        search_query = scholarly.search_pubs(query)
        
        for i, pub in enumerate(search_query):
            if i >= num_results:
                break
            
            bib = pub.get('bib', {})
            results.append({
                'source': 'Google Scholar',
                'title': bib.get('title', 'N/A'),
                'authors': ', '.join(bib.get('author', [])) if isinstance(bib.get('author'), list) else str(bib.get('author', 'N/A')),
                'year': str(bib.get('pub_year', 'N/A')),
                'abstract': bib.get('abstract', 'N/A')[:500],
                'url': pub.get('pub_url', pub.get('eprint_url', 'N/A')),
                'citations': pub.get('num_citations', 0),
                'venue': bib.get('venue', 'N/A')
            })
            print(f"  ✓ Artigo {i+1}: {bib.get('title', 'N/A')[:50]}...")
            
    except Exception as e:
        print(f"  ❌ Erro Google Scholar: {e}")
    
    print(f"  📊 Total Google Scholar: {len(results)} artigos")
    return results


def search_pubmed(query: str, num_results: int = 10) -> List[Dict]:
    """Busca no PubMed (API oficial)"""
    results = []
    print(f"🔍 Buscando no PubMed: {query}")
    
    try:
        # Buscar IDs
        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            'db': 'pubmed',
            'term': query,
            'retmax': num_results,
            'retmode': 'json'
        }
        
        response = requests.get(search_url, params=params, timeout=10)
        data = response.json()
        ids = data.get('esearchresult', {}).get('idlist', [])
        
        if not ids:
            print(f"  ⚠️  Nenhum resultado no PubMed")
            return results
        
        # Buscar detalhes
        fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        params = {
            'db': 'pubmed',
            'id': ','.join(ids),
            'retmode': 'xml'
        }
        
        response = requests.get(fetch_url, params=params, timeout=10)
        root = ET.fromstring(response.content)
        
        for article in root.findall('.//PubmedArticle'):
            try:
                title_elem = article.find('.//ArticleTitle')
                title = title_elem.text if title_elem is not None else 'N/A'
                
                authors = []
                for author in article.findall('.//Author'):
                    lastname = author.find('LastName')
                    forename = author.find('ForeName')
                    if lastname is not None and forename is not None:
                        authors.append(f"{forename.text} {lastname.text}")
                
                abstract_elem = article.find('.//AbstractText')
                abstract = abstract_elem.text if abstract_elem is not None else 'N/A'
                
                year_elem = article.find('.//PubDate/Year')
                year = year_elem.text if year_elem is not None else 'N/A'
                
                pmid_elem = article.find('.//PMID')
                pmid = pmid_elem.text if pmid_elem is not None else 'N/A'
                
                results.append({
                    'source': 'PubMed',
                    'title': title,
                    'authors': ', '.join(authors),
                    'year': year,
                    'abstract': abstract[:500] if abstract != 'N/A' else 'N/A',
                    'url': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    'citations': 'N/A',
                    'venue': 'PubMed'
                })
                
            except Exception as e:
                continue
                
    except Exception as e:
        print(f"  ❌ Erro PubMed: {e}")
    
    print(f"  📊 Total PubMed: {len(results)} artigos")
    return results


def search_arxiv(query: str, num_results: int = 10) -> List[Dict]:
    """Busca no arXiv (API oficial)"""
    results = []
    print(f"🔍 Buscando no arXiv: {query}")
    
    try:
        url = "http://export.arxiv.org/api/query"
        params = {
            'search_query': f'all:{query}',
            'start': 0,
            'max_results': num_results
        }
        
        response = requests.get(url, params=params, timeout=10)
        root = ET.fromstring(response.content)
        
        namespace = {'atom': 'http://www.w3.org/2005/Atom'}
        
        for entry in root.findall('atom:entry', namespace):
            title_elem = entry.find('atom:title', namespace)
            title = title_elem.text.strip() if title_elem is not None else 'N/A'
            
            authors = [
                author.find('atom:name', namespace).text
                for author in entry.findall('atom:author', namespace)
            ]
            
            summary_elem = entry.find('atom:summary', namespace)
            summary = summary_elem.text.strip() if summary_elem is not None else 'N/A'
            
            published_elem = entry.find('atom:published', namespace)
            published = published_elem.text[:4] if published_elem is not None else 'N/A'
            
            link_elem = entry.find('atom:id', namespace)
            link = link_elem.text if link_elem is not None else 'N/A'
            
            results.append({
                'source': 'arXiv',
                'title': title,
                'authors': ', '.join(authors),
                'year': published,
                'abstract': summary[:500] if summary != 'N/A' else 'N/A',
                'url': link,
                'citations': 'N/A',
                'venue': 'arXiv Preprint'
            })
            
    except Exception as e:
        print(f"  ❌ Erro arXiv: {e}")
    
    print(f"  📊 Total arXiv: {len(results)} artigos")
    return results


async def search_semantic_scholar_async(query: str, num_results: int = 10) -> List[Dict]:
    """Busca no Semantic Scholar"""
    results = []
    print(f"🔍 Buscando no Semantic Scholar: {query}")
    
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            'query': query,
            'limit': num_results,
            'fields': 'title,authors,year,abstract,citationCount,url,venue'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                data = await response.json()
                
                for paper in data.get('data', []):
                    authors = [a.get('name', '') for a in paper.get('authors', [])]
                    
                    results.append({
                        'source': 'Semantic Scholar',
                        'title': paper.get('title', 'N/A'),
                        'authors': ', '.join(authors),
                        'year': str(paper.get('year', 'N/A')),
                        'abstract': (paper.get('abstract', 'N/A') or 'N/A')[:500],
                        'url': paper.get('url', 'N/A'),
                        'citations': paper.get('citationCount', 0),
                        'venue': paper.get('venue', 'N/A')
                    })
                    
    except Exception as e:
        print(f"  ❌ Erro Semantic Scholar: {e}")
    
    print(f"  📊 Total Semantic Scholar: {len(results)} artigos")
    return results


async def search_openalex_async(query: str, num_results: int = 10) -> List[Dict]:
    """Busca no OpenAlex"""
    results = []
    print(f"🔍 Buscando no OpenAlex: {query}")
    
    try:
        url = "https://api.openalex.org/works"
        params = {
            'search': query,
            'per-page': num_results,
            'mailto': 'bot@example.com'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                data = await response.json()
                
                for work in data.get('results', []):
                    authors = [
                        authorship.get('author', {}).get('display_name', '')
                        for authorship in work.get('authorships', [])
                    ]
                    
                    abstract_inv = work.get('abstract_inverted_index', {})
                    abstract = 'N/A'
                    if abstract_inv:
                        words = [''] * (max(max(positions) for positions in abstract_inv.values()) + 1)
                        for word, positions in abstract_inv.items():
                            for pos in positions:
                                words[pos] = word
                        abstract = ' '.join(words)[:500]
                    
                    results.append({
                        'source': 'OpenAlex',
                        'title': work.get('title', 'N/A'),
                        'authors': ', '.join(authors[:5]),
                        'year': str(work.get('publication_year', 'N/A')),
                        'abstract': abstract,
                        'url': work.get('doi', work.get('id', 'N/A')),
                        'citations': work.get('cited_by_count', 0),
                        'venue': work.get('host_venue', {}).get('display_name', 'N/A')
                    })
                    
    except Exception as e:
        print(f"  ❌ Erro OpenAlex: {e}")
    
    print(f"  📊 Total OpenAlex: {len(results)} artigos")
    return results


async def search_all_sources(query: str, sources: List[str] = None) -> Dict:
    """Busca em múltiplas fontes"""
    
    if sources is None:
        sources = ['scholar', 'pubmed', 'arxiv', 'semantic', 'openalex']
    
    # Cache
    cache_key = hashlib.md5(f"{query}:{','.join(sorted(sources))}".encode()).hexdigest()
    
    if redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                print(f"✅ Resultado em cache!")
                return json.loads(cached)
        except:
            pass
    
    print(f"\n{'='*60}")
    print(f"🚀 INICIANDO BUSCA MULTI-SOURCE")
    print(f"Query: {query}")
    print(f"Fontes: {', '.join(sources)}")
    print(f"{'='*60}\n")
    
    results = {
        'query': query,
        'timestamp': datetime.now().isoformat(),
        'sources': {},
        'total_results': 0
    }
    
    # Async sources
    tasks = []
    if 'semantic' in sources:
        tasks.append(('semantic', search_semantic_scholar_async(query)))
    if 'openalex' in sources:
        tasks.append(('openalex', search_openalex_async(query)))
    
    for source_name, task in tasks:
        try:
            results['sources'][source_name] = await task
            results['total_results'] += len(results['sources'][source_name])
        except Exception as e:
            print(f"❌ Erro {source_name}: {e}")
            results['sources'][source_name] = []
    
    # Sync sources
    if 'scholar' in sources:
        try:
            results['sources']['scholar'] = await asyncio.to_thread(search_google_scholar, query)
            results['total_results'] += len(results['sources']['scholar'])
        except Exception as e:
            print(f"❌ Erro scholar: {e}")
            results['sources']['scholar'] = []
    
    if 'pubmed' in sources:
        try:
            results['sources']['pubmed'] = await asyncio.to_thread(search_pubmed, query)
            results['total_results'] += len(results['sources']['pubmed'])
        except Exception as e:
            print(f"❌ Erro pubmed: {e}")
            results['sources']['pubmed'] = []
    
    if 'arxiv' in sources:
        try:
            results['sources']['arxiv'] = await asyncio.to_thread(search_arxiv, query)
            results['total_results'] += len(results['sources']['arxiv'])
        except Exception as e:
            print(f"❌ Erro arxiv: {e}")
            results['sources']['arxiv'] = []
    
    print(f"\n{'='*60}")
    print(f"✅ BUSCA CONCLUÍDA: {results['total_results']} artigos encontrados")
    print(f"{'='*60}\n")
    
    # Salvar cache
    if redis_client:
        try:
            redis_client.setex(cache_key, 86400, json.dumps(results))
        except:
            pass
    
    return results


# ==========================================
# API ENDPOINTS
# ==========================================

class SearchRequest(BaseModel):
    query: str
    sources: Optional[List[str]] = None
    num_results: int = 10

@app.get("/")
async def root():
    """Página inicial"""
    return {
        "message": "🎓 Academic Research Bot API",
        "version": "1.0.0",
        "status": "online",
        "endpoints": {
            "/search": "POST - Buscar artigos",
            "/health": "GET - Health check",
            "/docs": "GET - Documentação interativa"
        },
        "sources": ["scholar", "pubmed", "arxiv", "semantic", "openalex"]
    }

@app.get("/health")
async def health_check():
    """Health check"""
    return {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'cache': 'enabled' if redis_client else 'disabled',
        'sources_available': ['scholar', 'pubmed', 'arxiv', 'semantic', 'openalex']
    }

@app.post("/search")
async def search_endpoint(request: SearchRequest):
    """Busca artigos em múltiplas fontes"""
    
    try:
        results = await search_all_sources(request.query, request.sources)
        return {
            'success': True,
            'data': results,
            'message': f'✅ Encontrados {results["total_results"]} artigos'
        }
    except Exception as e:
        print(f"❌ ERRO CRÍTICO: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)