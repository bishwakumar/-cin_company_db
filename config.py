DB_CONFIG = {
    "host": "localhost",
    "database": "cin_data",
    "user": "postgres",
    "password": "postgres",
    "port": 5432
}

SEARCH_API_URL = "https://api.startupindia.gov.in/sih/api/noauth/search/profiles"
PROFILE_API_URL = "https://api.startupindia.gov.in/sih/api/common/replica/user/profile/{profile_id}"
CIN_API_URL = "https://api.startupindia.gov.in/sih/api/noauth/dpiit/services/cin/info?cin={cin}"