from typing import Literal

import requests

from app import __version__
from app.config import settings
from app.logging import get_logger
from app.transcript import Transcript
from app.utils import write_to_json


logger = get_logger()


class Queuer:
    def __init__(self, test_mode=False):
        if not test_mode:
            self._config_endpoint()

    def _config_endpoint(self):
        self.url = settings.QUEUE_ENDPOINT + "/api"
        self.headers = {
            'Authorization': f'Bearer {settings.BEARER_TOKEN}',
            'Content-Type': 'application/json'
        }

    def push_to_queue(self, transcript_json):
        """Push the payload with the resulting transcript to the Queuer backend"""
        try:
            payload = {
                "content": transcript_json
            }
            response = requests.post(
                f"{self.url}/transcripts", json=payload, headers=self.headers)
            if response.status_code == 200:
                logger.info(
                    f"Transcript added to queue with id={response.json()['id']}")
            else:
                logger.error(
                    f"Transcript not added to queue: ({response.status_code}) {response.text}")
            return response
        except Exception as e:
            logger.error(f"Transcript not added to queue: {e}")

    def get_transcript(self, id):
        """Returns transcript based on ID from the Queuer backend"""
        response = requests.get(
            f"{self.url}/transcripts/{id}", headers=self.headers)
        return response.json()

    def _get_all_pages_from(self, url, params={}):
        query_params = {'page': 1}
        query_params.update(params)
        all_data = []

        while True:
            response = requests.get(
                url, headers=self.headers, params=query_params)
            data = response.json()

            # Process the current page's data
            all_data.extend(data['data'])

            # Check pagination information
            if not data['hasNextPage']:
                break  # Break the loop if there are no more pages

            # Update query_params to fetch the next page
            query_params['page'] += 1

        return all_data

    def get_queue(self):
        """Returns an array with all the transcripts in the queue"""
        return self._get_all_pages_from(f"{self.url}/transcripts")

    def get_reviews(self, status: Literal['expired', 'pending', 'active']):
        # TODO pagination for this endpoint has an issue, uncomment after fix
        # return self._get_all_pages_from(f"{self.url}/reviews/all", {"status": status})

        response = requests.get(
            f"{self.url}/reviews/all", headers=self.headers, params={"status": status})
        return response.json()["data"]

    def update_transcript(self, id, payload):
        response = requests.put(
            f"{self.url}/{id}", json=payload, headers=self.headers)
        return response.json()
