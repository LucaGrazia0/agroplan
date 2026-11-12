"""Diagnostica manuale OAuth: non viene eseguita durante i test offline."""
import os
from pathlib import Path
import httpx
from dotenv import load_dotenv


def main():
    load_dotenv(Path(__file__).with_name('.env'))
    if not os.getenv('COPERNICUS_CLIENT_ID') or not os.getenv('COPERNICUS_CLIENT_SECRET'):
        raise SystemExit('Configura le credenziali in backend/.env.')
    response = httpx.post(
        'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token',
        data={'grant_type':'client_credentials', 'client_id':os.environ['COPERNICUS_CLIENT_ID'],
              'client_secret':os.environ['COPERNICUS_CLIENT_SECRET']}, timeout=30)
    if response.is_success and response.json().get('access_token'):
        print('Connessione OAuth Copernicus riuscita.')
    else:
        raise SystemExit(f'Autenticazione fallita: HTTP {response.status_code}.')


if __name__ == '__main__':
    main()
