"""Strava API client for listing activities and downloading activity streams."""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from .activity import Activity


class StravaClientError(Exception):
    """Raised for errors interacting with the Strava API."""


class StravaClient:
    """Client for requesting Strava activity metadata and streams."""

    TOKEN_FILE = Path.home() / '.aitrainer' / 'strava_tokens.json'
    BASE_URL = 'https://www.strava.com/api/v3'
    STREAM_KEYS = 'time,altitude,heartrate,cadence,watts,velocity_smooth,distance'

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or self._load_access_token()
        self.headers = {'Authorization': f'Bearer {self.access_token}'}

    def _load_access_token(self) -> str:
        token = os.getenv('STRAVA_ACCESS_TOKEN')
        if token:
            return token.strip()

        if self.TOKEN_FILE.exists():
            with open(self.TOKEN_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            token = data.get('access_token') or data.get('accessToken')
            if token:
                return token.strip()

        raise StravaClientError(
            'Unable to find Strava access token. Set STRAVA_ACCESS_TOKEN or create ~/.aitrainer/strava_tokens.json with {"access_token": "..."}.'
        )

    def list_activities(self, after: datetime) -> List[Dict[str, Any]]:
        """List activities on Strava after a given date."""
        activities: List[Dict[str, Any]] = []
        page = 1
        per_page = 200

        while True:
            params = {
                'after': int(after.timestamp()),
                'per_page': per_page,
                'page': page,
            }
            response = requests.get(
                f'{self.BASE_URL}/athlete/activities',
                headers=self.headers,
                params=params,
                timeout=30,
            )
            if response.status_code != 200:
                raise StravaClientError(
                    f'Failed to load Strava activities: {response.status_code} {response.text}'
                )

            page_data = response.json()
            if not page_data:
                break

            activities.extend(page_data)
            if len(page_data) < per_page:
                break
            page += 1

        return activities

    def download_activity(self, activity_id: int) -> Activity:
        """Download a single activity and convert it to an Activity object."""
        metadata = self._get_activity_detail(activity_id)
        streams = self._get_activity_streams(activity_id)
        return self._build_activity(metadata, streams)

    def _get_activity_detail(self, activity_id: int) -> Dict[str, Any]:
        response = requests.get(
            f'{self.BASE_URL}/activities/{activity_id}',
            headers=self.headers,
            timeout=30,
        )
        if response.status_code != 200:
            raise StravaClientError(
                f'Failed to fetch activity detail: {response.status_code} {response.text}'
            )
        return response.json()

    def _get_activity_streams(self, activity_id: int) -> Dict[str, List[Any]]:
        response = requests.get(
            f'{self.BASE_URL}/activities/{activity_id}/streams',
            headers=self.headers,
            params={'keys': self.STREAM_KEYS, 'key_by_type': 'true'},
            timeout=30,
        )
        if response.status_code != 200:
            raise StravaClientError(
                f'Failed to fetch activity streams: {response.status_code} {response.text}'
            )

        return response.json()

    def _build_activity(self, metadata: Dict[str, Any], streams: Dict[str, Any]) -> Activity:
        start_date = metadata.get('start_date_local') or metadata.get('start_date')
        if not start_date:
            raise StravaClientError('Activity metadata is missing start time.')

        start_time = pd.to_datetime(start_date)
        if start_time.tzinfo is not None:
            start_time = start_time.tz_convert(None)

        time_stream = streams.get('time')
        if not time_stream:
            raise StravaClientError('No time stream available for activity.')

        time_values = time_stream.get('data') if isinstance(time_stream, dict) else time_stream
        if not time_values:
            raise StravaClientError('No time values found in the time stream.')

        data = {'timestamp': start_time + pd.to_timedelta(time_values, unit='s')}
        field_mapping = {
            'distance': 'distance',
            'altitude': 'altitude',
            'heartrate': 'heart_rate',
            'cadence': 'cadence',
            'watts': 'power',
            'velocity_smooth': 'speed',
        }

        for stream_key, column_name in field_mapping.items():
            stream = streams.get(stream_key)
            if stream is not None:
                data[column_name] = stream["data"]

        activity = Activity(
            sport=metadata.get('sport') or metadata.get('type') or 'cycling',
            start_time=start_time,
            total_distance=metadata.get('distance'),
            total_elapsed_time=metadata.get('elapsed_time'),
            data=pd.DataFrame(data),
        )

        return activity
