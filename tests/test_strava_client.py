"""Tests for StravaClient with mocked API calls"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime
from src.data import StravaClient, StravaClientError, Activity
import pandas as pd


class TestStravaClient:
    """Test StravaClient with mocked HTTP requests"""
    
    @pytest.fixture
    def mock_client(self):
        fake_tokens = {
            'access_token': 'test_token',
            'refresh_token': 'test_refresh',
            'strava_client_id': '12345',
            'strava_client_secret': 'test_secret',
        }
        with patch.object(StravaClient, '_load_tokens', return_value=fake_tokens), \
             patch.object(StravaClient, '_check_and_refresh_token'):
            client = StravaClient()
        client._check_and_refresh_token = Mock()
        return client
    
    def test_list_activities_success(self, mock_client):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 123,
                'name': 'Test Ride',
                'start_date': '2023-01-01T10:00:00Z',
                'distance': 10000,
                'elapsed_time': 1800
            }
        ]
        
        with patch('requests.get', return_value=mock_response) as mock_get:
            activities = mock_client.list_activities(datetime(2023, 1, 1))
            
            assert len(activities) == 1
            assert activities[0]['id'] == 123
            mock_get.assert_called_once()
    
    def test_list_activities_pagination(self, mock_client):
        # Mock multiple pages - first page full (200 items), second partial, third empty
        page1_data = [{'id': i} for i in range(200)]
        page2_data = [{'id': i} for i in range(200, 203)]
        responses = [
            Mock(status_code=200, json=Mock(return_value=page1_data)),
            Mock(status_code=200, json=Mock(return_value=page2_data)),
            Mock(status_code=200, json=Mock(return_value=[]))  # Empty to stop
        ]
        
        with patch('requests.get', side_effect=responses) as mock_get:
            activities = mock_client.list_activities(datetime(2023, 1, 1))
            
            assert len(activities) == 203
            assert mock_get.call_count == 2
    
    def test_download_activity_success(self, mock_client):
        # Mock metadata
        metadata = {
            'id': 123,
            'sport': 'Ride',
            'start_date_local': '2023-01-01T10:00:00Z',
            'distance': 10000,
            'elapsed_time': 1800
        }
        
        # Mock streams
        streams = {
            'time': {'data': [0, 10, 20]},
            'distance': {'data': [0, 100, 200]},
            'watts': {'data': [200, 210, 220]},
            'heartrate': {'data': [120, 130, 140]}
        }
        
        with patch.object(mock_client, '_get_activity_detail', return_value=metadata), \
             patch.object(mock_client, '_get_activity_streams', return_value=streams):
            activity = mock_client.download_activity(123)
            
            assert isinstance(activity, Activity)
            assert activity.sport == 'Ride'
            assert len(activity.data) == 3
            assert 'power' in activity.data.columns
            assert 'heart_rate' in activity.data.columns
    
    def test_download_activity_missing_streams(self, mock_client):
        metadata = {
            'id': 123,
            'sport': 'Ride',
            'start_date_local': '2023-01-01T10:00:00Z',
            'distance': 10000,
            'elapsed_time': 1800
        }
        streams = {
            # Missing time stream
            'distance': {'data': [0, 100]},
        }
        
        with patch.object(mock_client, '_get_activity_detail', return_value=metadata), \
             patch.object(mock_client, '_get_activity_streams', return_value=streams):
            with pytest.raises(StravaClientError, match="No time stream available for activity"):
                mock_client.download_activity(123)
    
    def test_download_activity_api_error(self, mock_client):
        with patch.object(mock_client, '_get_activity_detail', side_effect=StravaClientError("API Error")):
            with pytest.raises(StravaClientError):
                mock_client.download_activity(123)