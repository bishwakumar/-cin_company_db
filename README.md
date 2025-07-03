![Visitors](https://visitor-badge.laobi.icu/badge?page_id=bishwakumar.cin-company-database)

# CIN Company Database Builder
A Python tool to build a searchable database of Indian company records using CIN, Startup India APIs, and PostgreSQL.

> **Note:** This project can be especially useful for developers looking for an API-based solution to fetch company details using a Corporate Identification Number (CIN), until Startup India allows direct access.

---

**Important:**
When making requests to the Startup India APIs, you must set the appropriate headers (such as `User-Agent`, `Origin`, and `Referer`) and ensure the request source mimics a browser. Otherwise, the API will not respond to requests made from tools like Postman.

Example headers:
```http
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36
Origin: https://www.startupindia.gov.in
Referer: https://www.startupindia.gov.in/
Accept: application/json, text/javascript, */*; q=0.01
Content-Type: application/json
```

---

## Overview

This project is designed to build a comprehensive database of company records by leveraging public APIs provided by Startup India. The workflow involves searching for company profiles, fetching detailed information for each profile, and then retrieving additional data using the company's CIN (Corporate Identification Number). The system is built with scalability in mind, using queues to manage and process large volumes of data efficiently.

---

## Project Structure

```
CIN/
  ├── api/
  │   ├── cin.py
  │   ├── export.py
  │   ├── profile.py
  │   ├── search.py
  │   └── sync.py
  ├── db/
  │   └── models.py
  ├── utils/
  │   └── logger.py
  ├── config.py
  ├── main.py
  └── search_progress.json
```

---

## What Are We Building?

We are building a local database of Indian company records. The process involves:

1. **Searching for companies** using the public search API, iterating through all alphabets and paginated results.
2. **Fetching detailed profiles** for each company using their unique profile ID.
3. **Retrieving CIN-specific data** for each company using the Corporate Identification Number (CIN) obtained from the profile details.
4. **Storing all collected data** in a local PostgreSQL database for further analysis or export.

---

## API Endpoints Used

### 1. Search API

- **Endpoint:**  
  `https://api.startupindia.gov.in/sih/api/noauth/search/profiles`
- **Purpose:**  
  To search for company profiles. The API supports pagination and can be filtered by the starting alphabet of the company name.
- **Usage:**  
  The system iterates through all alphabets (A-Z) and paginates through the results to collect all available company profile IDs.
- **Sample Response:**
  ```json
  {
    "content": [
      {
        "id": "12345",
        "name": "Acme Innovations",
        "country": "India",
        "state": "Karnataka",
        "city": "Bangalore"
        // ...other fields
      },
      {
        "id": "67890",
        "name": "Beta Startups",
        "country": "India",
        "state": "Maharashtra",
        "city": "Mumbai"
        // ...other fields
      }
    ],
    "totalElements": 2,
    "totalPages": 1,
    "size": 10,
    "number": 0
  }
  ```

### 2. Profile API

- **Endpoint:**  
  `https://api.startupindia.gov.in/sih/api/common/replica/user/profile/{profile_id}`
- **Purpose:**  
  To fetch detailed information about a company using its profile ID obtained from the search API.
- **Usage:**  
  For each profile ID collected, a request is made to this endpoint to retrieve comprehensive company details, including the CIN.
- **Sample Response:**
  ```json
  {
    "user": {
      "startup": {
        "cin": "U12345KA2020XXX123456",
        "pan": "ABCDE1234F",
        "members": [
          {
            "name": "Vijay",
            "role": "Founder"
          }
        ]
        // ...other fields
      }
      // ...other fields
    }
    // ...other fields
  }
  ```

### 3. CIN API

- **Endpoint:**  
  `https://api.startupindia.gov.in/sih/api/noauth/dpiit/services/cin/info?cin={cin}`
- **Purpose:**  
  To fetch additional company information using the Corporate Identification Number (CIN) obtained from the profile details.
- **Usage:**  
  For each company, the CIN is used to call this API and enrich the database with more granular data.
- **Sample Response:**
  ```json
  {
    "data": {
      "cin": "U12345KA2020XXX123456",
      "email": "info@acmeinnovations.com",
      "incorpdate": "2020-01-15",
      "registeredAddress": "123, Main Road, Bangalore, Karnataka, India",
      "registeredContactNo": "+91-9876543210"
      // ...other fields
    },
    "status": "SUCCESS"
  }
  ```

---

## Data Collection Workflow

1. **Search Phase:**  
   - Iterate through all alphabets (A-Z).
   - For each alphabet, paginate through the search results.
   - Collect all profile IDs.

2. **Profile Fetch Phase:**  
   - For each profile ID, call the Profile API.
   - Extract the CIN from the profile data.

3. **CIN Data Fetch Phase:**  
   - For each CIN, call the CIN API.
   - Store the combined data in the local database.

---

## Queue Implementation

To efficiently handle the large volume of API requests and data processing, the project uses queues at each stage:

- **Search Queue:**  
  Manages the list of (alphabet, page) combinations to be processed. Ensures that all possible search queries are covered and can be retried if interrupted.

- **Profile Queue:**  
  Stores profile IDs fetched from the search API. Each profile ID is processed to fetch detailed information.

- **CIN Queue:**  
  Stores CIN numbers extracted from profile details. Each CIN is processed to fetch additional company data.

**Benefits of Using Queues:**
- **Resilience:** If the process is interrupted, queues allow resuming from where it left off.
- **Scalability:** Queues decouple the stages, allowing for parallel processing and easier scaling.
- **Progress Tracking:** The `search_progress.json` file is used to track progress and avoid duplicate processing.

---

## Configuration

All API endpoints and database credentials are stored in `config.py`:

```python
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
```

---

## How to Run

1. **Install dependencies** (if any, e.g., `requests`, `psycopg2`).
2. **Set up PostgreSQL** using the credentials in `config.py`.
3. **Run the main script:**
   ```bash
   python main.py
   ```
4. The script will automatically manage the queues and populate the database.

---

## Contributing

Feel free to open issues or submit pull requests for improvements or bug fixes!

---
