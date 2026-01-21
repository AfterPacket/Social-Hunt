from __future__ import annotations

import time
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Tuple

from ..providers_base import BaseProvider
from ..types import ProviderResult, ResultStatus


class PeekYouProvider(BaseProvider):
    name = "peekyou"
    timeout = 15
    ua_profile = "desktop_chrome"
    
    # US states mapping from abbreviations to full names
    US_STATES = {
        # States
        'al': 'alabama', 'ak': 'alaska', 'az': 'arizona', 'ar': 'arkansas',
        'ca': 'california', 'co': 'colorado', 'ct': 'connecticut', 'de': 'delaware',
        'fl': 'florida', 'ga': 'georgia', 'hi': 'hawaii', 'id': 'idaho',
        'il': 'illinois', 'in': 'indiana', 'ia': 'iowa', 'ks': 'kansas',
        'ky': 'kentucky', 'la': 'louisiana', 'me': 'maine', 'md': 'maryland',
        'ma': 'massachusetts', 'mi': 'michigan', 'mn': 'minnesota', 'ms': 'mississippi',
        'mo': 'missouri', 'mt': 'montana', 'ne': 'nebraska', 'nv': 'nevada',
        'nh': 'new_hampshire', 'nj': 'new_jersey', 'nm': 'new_mexico', 'ny': 'new_york',
        'nc': 'north_carolina', 'nd': 'north_dakota', 'oh': 'ohio', 'ok': 'oklahoma',
        'or': 'oregon', 'pa': 'pennsylvania', 'ri': 'rhode_island', 'sc': 'south_carolina',
        'sd': 'south_dakota', 'tn': 'tennessee', 'tx': 'texas', 'ut': 'utah',
        'vt': 'vermont', 'va': 'virginia', 'wa': 'washington', 'wv': 'west_virginia',
        'wi': 'wisconsin', 'wy': 'wyoming',
        
        # Territories
        'dc': 'washington_dc', 'pr': 'puerto_rico', 'gu': 'guam',
        'vi': 'virgin_islands', 'mp': 'northern_mariana_islands', 'as': 'american_samoa'
    }
    
    def __init__(self, state: Optional[str] = None):
        """
        Initialize PeekYou provider.
        
        Args:
            state: Optional US state abbreviation or full name (e.g., 'pa', 'pennsylvania', 'new-york')
        """
        super().__init__()
        self.state = self._normalize_state(state) if state else None
    
    def _normalize_state(self, state_input: str) -> str:
        """
        Normalize state input to full state name with underscores.
        
        Args:
            state_input: State abbreviation or name
            
        Returns:
            Normalized state name
        """
        # Clean the input
        state_clean = state_input.strip().lower().replace(" ", "_").replace("-", "_")
        
        # Check if it's a state abbreviation (2 letters)
        if len(state_clean) == 2 and state_clean in self.US_STATES:
            return self.US_STATES[state_clean]
        
        # Check if it's already a full state name
        for abbrev, full_name in self.US_STATES.items():
            if state_clean == full_name or state_clean == abbrev:
                return full_name
        
        # If not found, assume it's already in the correct format
        return state_clean
    
    def _parse_input(self, input_str: str) -> Tuple[str, Optional[str]]:
        """
        Parse input string to extract name and optional state.
        
        Supports formats:
        - "name"
        - "state/name"
        - "name, state"
        
        Args:
            input_str: Raw input string
            
        Returns:
            Tuple of (name, state)
        """
        # Remove extra whitespace
        input_str = input_str.strip()
        
        # Check for state/name format (e.g., "pa/john_doe" or "pennsylvania/john_doe")
        if '/' in input_str:
            parts = input_str.split('/', 1)
            state_part = parts[0].strip()
            name_part = parts[1].strip()
            state = self._normalize_state(state_part)
            return name_part, state
        
        # Check for name, state format (e.g., "john doe, pa" or "john doe, pennsylvania")
        if ',' in input_str:
            parts = input_str.split(',', 1)
            name_part = parts[0].strip()
            state_part = parts[1].strip()
            state = self._normalize_state(state_part)
            return name_part, state
        
        # No state specified
        return input_str, None
    
    def _format_name_for_url(self, name: str) -> str:
        """
        Format name for PeekYou URL.
        
        Converts:
        - Spaces to underscores
        - Hyphens to plus signs for multi-part last names
        - Multiple spaces to single underscores
        
        Args:
            name: Raw name input
            
        Returns:
            Formatted name for URL
        """
        # First, normalize the name
        name_lower = name.lower().strip()
        
        # Replace hyphens with plus signs for multi-part names
        # e.g., "shaw-gallagher" -> "shaw+gallagher"
        name_with_plus = name_lower.replace("-", "+")
        
        # Replace spaces with underscores
        name_with_underscores = name_with_plus.replace(" ", "_")
        
        # Clean up any double underscores or plus signs
        import re
        name_clean = re.sub(r'_{2,}', '_', name_with_underscores)
        name_clean = re.sub(r'\+{2,}', '+', name_clean)
        
        return name_clean
    
    def build_url(self, query: str, state_override: Optional[str] = None) -> str:
        """
        Build PeekYou URL from a query string.
        
        Args:
            query: Query string (can include state info)
            state_override: Optional state override
            
        Returns:
            URL string
        """
        # Parse the input to get name and state
        name, parsed_state = self._parse_input(query)
        
        # Use state in order of priority: override > parsed > instance state
        state_to_use = state_override or parsed_state or self.state
        
        # Format the name for URL
        name_formatted = self._format_name_for_url(name)
        
        if state_to_use:
            # State-specific URL: https://www.peekyou.com/usa/{state}/{name}
            return f"https://www.peekyou.com/usa/{state_to_use}/{name_formatted}"
        else:
            # General URL: https://www.peekyou.com/{name}
            return f"https://www.peekyou.com/{name_formatted}"
    
    async def check(self, query: str, client, headers) -> ProviderResult:
        """
        Check for a person on PeekYou.
        
        Args:
            query: Query string (name, or state/name format)
            client: HTTP client
            headers: Request headers
            
        Returns:
            ProviderResult object
        """
        # Parse the query to extract name
        name, parsed_state = self._parse_input(query)
        
        url = self.build_url(query)
        start = time.monotonic()
        ts = datetime.now(timezone.utc).isoformat()
        
        try:
            r = await client.get(
                url,
                timeout=self.timeout,
                follow_redirects=True,
                headers=headers
            )
            text = (r.text or "").lower()
            
            # Determine status based on response
            if r.status_code == 404:
                status = ResultStatus.NOT_FOUND
            elif "this peekyou profile has been removed" in text:
                status = ResultStatus.NOT_FOUND
            elif "no results found" in text:
                status = ResultStatus.NOT_FOUND
            elif "profile not found" in text:
                status = ResultStatus.NOT_FOUND
            elif "privacy settings" in text:
                status = ResultStatus.FOUND
            elif "profile preview" in text:
                status = ResultStatus.FOUND
            elif "age" in text and "location" in text:
                status = ResultStatus.FOUND
            elif name.lower() in text or self._format_name_for_url(name).replace("_", " ") in text:
                # Name appears on page
                status = ResultStatus.FOUND
            else:
                status = ResultStatus.UNKNOWN
            
            # Extract profile information
            profile = {}
            if status == ResultStatus.FOUND:
                profile = self._extract_profile_info(text, name)
            
            # Get the actual state used
            state_used = parsed_state or self.state
            
            return ProviderResult(
                provider=self.name,
                username=name,  # Using the parsed name
                url=url,
                status=status,
                http_status=r.status_code,
                elapsed_ms=int((time.monotonic() - start) * 1000),
                evidence={
                    "len": len(text),
                    "state": state_used,
                    "has_privacy_notice": "privacy settings" in text,
                    "original_query": query,
                    "parsed_name": name,
                    "formatted_url_name": self._format_name_for_url(name)
                },
                profile=profile,
                timestamp_iso=ts,
            )
            
        except Exception as e:
            # Parse the query to extract name for error result
            name, _ = self._parse_input(query)
            
            return ProviderResult(
                provider=self.name,
                username=name,
                url=url,
                status=ResultStatus.ERROR,
                error=str(e),
                elapsed_ms=int((time.monotonic() - start) * 1000),
                profile={},
                timestamp_iso=ts,
            )
    
    def _extract_profile_info(self, text: str, name: str) -> dict:
        """
        Extract basic profile information from PeekYou page.
        
        Args:
            text: HTML text content
            name: Full name
            
        Returns:
            Dictionary with extracted profile info
        """
        profile = {}
        
        # Split name if possible
        name_parts = name.split()
        if len(name_parts) >= 2:
            profile["first_name"] = name_parts[0]
            profile["last_name"] = " ".join(name_parts[1:])
        
        # Look for age pattern
        age_patterns = [
            r'(\d{1,3})\s+years?\s+old',
            r'age\s*:\s*(\d{1,3})',
            r'(\d{1,3})\s+yrs?',
            r'age\s+(\d{1,3})',
        ]
        
        for pattern in age_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                profile["age"] = match.group(1)
                break
        
        # Try to find location
        location_patterns = [
            r'lives?\s+in\s+([^<>.]+?)(?:<|\.|$)',
            r'location\s*:\s*([^<>.]+?)(?:<|\.|$)',
            r'from\s+([^<>.]+?)(?:<|\.|$)',
            r'city\s*:\s*([^<>.]+?)(?:<|\.|$)',
        ]
        
        for pattern in location_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                if len(location) < 100:
                    profile["location"] = location
                break
        
        # Try to extract social media links
        social_media = {}
        social_patterns = {
            "facebook": r'facebook\.com/[^"\'>]+',
            "twitter": r'twitter\.com/[^"\'>]+',
            "instagram": r'instagram\.com/[^"\'>]+',
            "linkedin": r'linkedin\.com/[^"\'>]+',
            "pinterest": r'pinterest\.com/[^"\'>]+',
        }
        
        for platform, pattern in social_patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                social_media[platform] = list(set(matches))[:3]  # Limit to 3 unique links
        
        if social_media:
            profile["social_media"] = social_media
        
        return profile


# Create provider instance
PROVIDERS = [PeekYouProvider()]