"""FIT file parser for reading Garmin activity files"""
from pathlib import Path
from typing import Optional
import pandas as pd
from fitparse import FitFile

from .activity import Activity


class FITParser:
    """Parses FIT files and creates Activity objects"""
    
    # Map FIT message types to our data columns
    FIELD_MAPPING = {
        'power': 'power',
        'heart_rate': 'heart_rate',
        'cadence': 'cadence',
        'speed': 'speed',
        'distance': 'distance',
        'altitude': 'altitude',
    }
    
    @staticmethod
    def parse(fit_file_path: str | Path) -> Optional[Activity]:
        """
        Parse a FIT file and return an Activity object
        
        Args:
            fit_file_path: Path to the .fit file
            
        Returns:
            Activity object or None if parsing fails
        """
        fit_file_path = Path(fit_file_path)
        
        if not fit_file_path.exists():
            raise FileNotFoundError(f"FIT file not found: {fit_file_path}")
        
        if fit_file_path.suffix.lower() != '.fit':
            raise ValueError(f"Expected .fit file, got: {fit_file_path.suffix}")
        
        try:
            fit = FitFile(str(fit_file_path))
        except Exception as e:
            raise RuntimeError(f"Failed to parse FIT file: {e}")
        
        # Extract metadata
        activity_metadata = FITParser._extract_metadata(fit)
        
        # Extract record data
        records = FITParser._extract_records(fit)
        
        if not records:
            raise ValueError("No record data found in FIT file")
        
        # Create DataFrame
        df = pd.DataFrame(records)
        
        # Create Activity
        activity = Activity(
            sport=activity_metadata.get('sport', 'cycling'),
            start_time=activity_metadata.get('start_time'),
            total_distance=activity_metadata.get('total_distance'),
            total_elapsed_time=activity_metadata.get('total_elapsed_time'),
            data=df
        )
        
        return activity
    
    @staticmethod
    def _extract_metadata(fit: FitFile) -> dict:
        """Extract session/activity metadata"""
        metadata = {}
        
        # Look for file_id message
        for message in fit.messages:
            if message.name == 'file_id':
                for field in message.fields:
                    if field.name == 'created':
                        metadata['start_time'] = str(field.value)
                break
        
        # Look for session message
        for message in fit.messages:
            if message.name == 'session':
                for field in message.fields:
                    if field.name == 'sport':
                        metadata['sport'] = str(field.value)
                    elif field.name == 'total_distance':
                        metadata['total_distance'] = field.value
                    elif field.name == 'total_elapsed_time':
                        metadata['total_elapsed_time'] = field.value
                break
        
        return metadata
    
    @staticmethod
    def _extract_records(fit: FitFile) -> list[dict]:
        """Extract record data from FIT file"""
        records = []
        
        for message in fit.messages:
            if message.name != 'record':
                continue
            
            record = {}
            for field in message.fields:
                # Always include timestamp
                if field.name == 'timestamp':
                    record['timestamp'] = field.value
                # Include specified fields if they exist
                elif field.name in FITParser.FIELD_MAPPING:
                    record[FITParser.FIELD_MAPPING[field.name]] = field.value
            
            # Only add records that have a timestamp
            if 'timestamp' in record:
                records.append(record)
        
        # Sort by timestamp
        records.sort(key=lambda x: x['timestamp'])
        
        return records
    
    @staticmethod
    def find_fit_files(directory: str | Path) -> list[Path]:
        """
        Find all .fit files in a directory
        
        Args:
            directory: Directory to search
            
        Returns:
            List of Path objects for .fit files found
        """
        directory = Path(directory)
        return sorted(directory.glob('*.fit')) + sorted(directory.glob('**/*.fit'))
