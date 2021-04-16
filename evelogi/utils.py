from urllib.parse import urlparse, urljoin, urlencode

from flask import request, redirect, url_for, current_app

def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

def redirect_back(default='main.index', **kwargs):
    for target in request.args.get('next'), request.referrer:
        if not target:
            continue
        if is_safe_url(target):
            return redirect(target)
    return redirect(url_for(default, **kwargs))

def eve_oauth_url():
    params = {
        'response_type': current_app.config['RESPONSE_TYPE'],
        'redirect_uri': current_app.config['REDIRECT_URL'],
        'client_id': current_app.config['CLIENT_ID'],
        'scope': current_app.config['SCOPE'],
        'state': current_app.config['STATE'],
    }

    return str(current_app.config['OAUTH_URL'] + urlencode(params))