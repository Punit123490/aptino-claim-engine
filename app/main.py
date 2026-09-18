import asyncio
import json
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import ROOT, get_settings
from app.models import ClaimCase, ClaimResult
from app.retrieval import PolicyIndex
from app.workflow import ClaimWorkflow

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.index = None
    app.state.error = None
    app.state.busy = asyncio.Semaphore(2)

    async def load():
        try:
            app.state.index = await asyncio.to_thread(PolicyIndex, get_settings())
        except Exception as exc:
            app.state.error = type(exc).__name__
            logger.error('Index initialization failed (%s)', type(exc).__name__)

    loading = asyncio.create_task(load())
    yield
    if not loading.done():
        loading.cancel()


app = FastAPI(title='Policy Review API', version='1.0.0', lifespan=lifespan)


@app.middleware('http')
async def request_limits(request: Request, call_next):
    if request.method == 'POST':
        # Check actual bytes, including chunked requests without Content-Length.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 100_000:
                return JSONResponse({'detail': 'Request exceeds 100 KB.'}, status_code=413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    if request.url.path.startswith('/analyze'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    # Do not echo request values; users may accidentally submit sensitive text.
    return JSONResponse(status_code=422, content={'detail': [
        {'loc': list(e['loc']), 'msg': e['msg'], 'type': e['type']} for e in exc.errors()
    ]})


def authorize(request: Request):
    expected = get_settings().app_api_token.get_secret_value()
    supplied = request.headers.get('authorization', '').removeprefix('Bearer ')
    if expected and not secrets.compare_digest(expected, supplied):
        raise HTTPException(401, 'A valid reviewer access token is required.')


@app.get('/health')
def health():
    settings = get_settings()
    index = getattr(app.state, 'index', None)
    configured = bool(settings.google_api_key.get_secret_value())
    ready = index is not None and configured
    return JSONResponse(status_code=200 if ready else 503, content={
        'status': 'ready' if ready else 'not_ready', 'index_ready': index is not None,
        'model_configured': configured, 'model': settings.gemini_model,
        'chunks': len(index.chunks) if index else 0,
        'policy_sha256': index.policy_sha256 if index else None,
        'error': getattr(app.state, 'error', None),
    })


@app.get('/cases')
def cases():
    return json.loads((ROOT / 'data/candidate_data/public_test_cases.json').read_text(encoding='utf-8'))


@app.get('/policy')
def policy():
    return FileResponse(get_settings().policy_path, media_type='application/pdf')


@app.post('/analyze', response_model=ClaimResult, dependencies=[Depends(authorize)])
async def analyze(case: ClaimCase):
    if case.policy_id != 'USGIC-CSC-2017-2018':
        raise HTTPException(422, 'Unsupported policy_id. This service indexes only USGIC-CSC-2017-2018.')
    settings = get_settings()
    index = getattr(app.state, 'index', None)
    if index is None or not settings.google_api_key.get_secret_value():
        raise HTTPException(503, 'Service is not ready. Check /health and the server configuration.')
    semaphore = app.state.busy
    if semaphore.locked():
        raise HTTPException(429, 'Both review slots are busy. Please retry shortly.', headers={'Retry-After': '10'})
    async with semaphore:
        workflow = ClaimWorkflow(settings, index)
        result = await asyncio.to_thread(workflow.analyze, case)
    if result.reason_code == 'MODEL_OR_TOOL_UNAVAILABLE':
        return JSONResponse(status_code=503, content=result.model_dump(mode='json'))
    return result


app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')


@app.get('/', include_in_schema=False)
def home():
    return FileResponse(ROOT / 'static/index.html')
