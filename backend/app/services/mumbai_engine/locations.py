"""
Mumbai 8 Monitored Locations Metadata & Hotspot Evidence Reference.
Based on Mumbai Municipal Corporation (BMC) flood preparedness guidelines
and historical climate action studies.
"""
from typing import Dict, Any, List

MUMBAI_LOCATIONS: List[Dict[str, Any]] = [
    {
        "location_id": "mum_andheri",
        "location_name": "Andheri",
        "latitude": 19.1197,
        "longitude": 72.8464,
        "elevation_m": 16.0,
        "hotspot_evidence": {
            "reported_evidence": "Andheri East appears in reported waterlogging-prone areas (subway & junction)",
            "match_status": "NEARBY_AREA_ONLY",
            "source": "Mid-day, BMC Flood Preparedness Guidelines 2026 coverage",
            "source_date": "2026-08-05",
            "risk_label_usable": False
        }
    },
    {
        "location_id": "mum_bandra",
        "location_name": "Bandra",
        "latitude": 19.0607,
        "longitude": 72.8362,
        "elevation_m": 15.0,
        "hotspot_evidence": {
            "reported_evidence": "Bandra appears among recurring waterlogging areas (Linking Rd & SV Rd junctions)",
            "match_status": "LOCALITY_REPORTED",
            "source": "Mid-day, BMC Flood Preparedness Guidelines 2026 coverage",
            "source_date": "2026-07-27",
            "risk_label_usable": False
        }
    },
    {
        "location_id": "mum_chembur",
        "location_name": "Chembur",
        "latitude": 19.0522,
        "longitude": 72.8990,
        "elevation_m": 15.0,
        "hotspot_evidence": {
            "reported_evidence": "No exact match established from sources reviewed",
            "match_status": "UNVERIFIED",
            "source": None,
            "source_date": None,
            "risk_label_usable": False
        }
    },
    {
        "location_id": "mum_colaba",
        "location_name": "Colaba",
        "latitude": 18.9067,
        "longitude": 72.8147,
        "elevation_m": 12.0,
        "hotspot_evidence": {
            "reported_evidence": "No exact match established from sources reviewed",
            "match_status": "UNVERIFIED",
            "source": None,
            "source_date": None,
            "risk_label_usable": False
        }
    },
    {
        "location_id": "mum_dadar",
        "location_name": "Dadar",
        "latitude": 19.0178,
        "longitude": 72.8478,
        "elevation_m": 10.0,
        "hotspot_evidence": {
            "reported_evidence": "Dadar appears in a historical heavy-rainfall cluster analysis (Hindmata & TT Circle)",
            "match_status": "RAINFALL_CONTEXT_ONLY",
            "source": "Mumbai Climate Action Plan, 2022",
            "source_date": "2022",
            "risk_label_usable": False
        }
    },
    {
        "location_id": "mum_kurla",
        "location_name": "Kurla",
        "latitude": 19.0726,
        "longitude": 72.8845,
        "elevation_m": 7.0,
        "hotspot_evidence": {
            "reported_evidence": "Recurring waterlogging reported in Kurla (Bail Bazar & LBS Marg low-lying basin)",
            "match_status": "LOCALITY_REPORTED",
            "source": "Mid-day, BMC Flood Preparedness Guidelines 2026 coverage",
            "source_date": "2026-07-27",
            "risk_label_usable": False
        }
    },
    {
        "location_id": "mum_powai",
        "location_name": "Powai",
        "latitude": 19.1176,
        "longitude": 72.9060,
        "elevation_m": 43.0,
        "hotspot_evidence": {
            "reported_evidence": "Recurring waterlogging reported in the Mithi catchment lower approaches",
            "match_status": "LOCALITY_REPORTED",
            "source": "Mid-day, BMC Flood Preparedness Guidelines 2026 coverage",
            "source_date": "2026-07-27",
            "risk_label_usable": False
        }
    },
    {
        "location_id": "mum_sion",
        "location_name": "Sion",
        "latitude": 19.0434,
        "longitude": 72.8619,
        "elevation_m": 8.0,
        "hotspot_evidence": {
            "reported_evidence": "No exact match established from sources reviewed (Sion circle low-lying chronic spot)",
            "match_status": "UNVERIFIED",
            "source": None,
            "source_date": None,
            "risk_label_usable": False
        }
    }
]

def get_mumbai_locations() -> List[Dict[str, Any]]:
    return MUMBAI_LOCATIONS

def get_location_by_name(name: str) -> Dict[str, Any]:
    name_clean = name.strip().lower()
    for loc in MUMBAI_LOCATIONS:
        if loc["location_name"].lower() == name_clean or loc["location_id"].lower() == name_clean:
            return loc
    return None
