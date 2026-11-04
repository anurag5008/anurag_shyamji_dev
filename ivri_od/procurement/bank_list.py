# Copyright (c) 2026, Profezzo and contributors
"""The banks that can be chosen in the Mark as completed form (they are kept in the Bank list of the desk, so the client can add or remove any).

Compiled on 2 November 2026 from:
  - Wikipedia, "List of banks in India" (public sector, private sector, small finance, payments, foreign and local area banks;
    it follows the Reserve Bank of India lists): https://en.wikipedia.org/wiki/List_of_banks_in_India
  - Odisha Grameen Bank (formed on 1 May 2025 from Odisha Gramya Bank and Utkal Grameen Bank): https://en.wikipedia.org/wiki/Odisha_Grameen_Bank
  - Odisha State Co-operative Bank, "Chief Executive Officers of DCCBs" (the 17 District Central Co-operative Banks of Odisha):
    https://odishascb.bank.in/chief_executive_officers.php
Please confirm the list with the client; new banks are added in the Bank list.
"""

PUBLIC_SECTOR = (
	"Bank of Baroda", "Bank of India", "Bank of Maharashtra", "Canara Bank", "Central Bank of India", "Indian Bank", "Indian Overseas Bank",
	"Punjab & Sind Bank", "Punjab National Bank", "State Bank of India", "UCO Bank", "Union Bank of India",
)

PRIVATE_SECTOR = (
	"Axis Bank", "Bandhan Bank", "CSB Bank", "City Union Bank", "DCB Bank", "Dhanlaxmi Bank", "Federal Bank", "HDFC Bank", "ICICI Bank", "IDBI Bank",
	"IDFC First Bank", "IndusInd Bank", "Jammu & Kashmir Bank", "Karnataka Bank", "Karur Vysya Bank", "Kotak Mahindra Bank", "Nainital Bank",
	"RBL Bank", "South Indian Bank", "Tamilnad Mercantile Bank", "Yes Bank",
)

SMALL_FINANCE = (
	"AU Small Finance Bank", "Capital Small Finance Bank", "Equitas Small Finance Bank", "ESAF Small Finance Bank", "Jana Small Finance Bank",
	"Shivalik Small Finance Bank", "Slice Small Finance Bank", "Suryoday Small Finance Bank", "Ujjivan Small Finance Bank", "Unity Small Finance Bank",
	"Utkarsh Small Finance Bank",
)

PAYMENTS = (
	"Airtel Payments Bank", "Fino Payments Bank", "India Post Payments Bank", "Jio Payments Bank", "NSDL Payments Bank",
)

LOCAL_AREA = ("Coastal Local Area Bank", "Krishna Bhima Samruddhi Local Area Bank")

FOREIGN = (
	"DBS Bank India", "SBM Bank India", "Australia & New Zealand Banking Group", "Bank of Bahrain and Kuwait", "AB Bank", "Sonali Bank", "Bank of Nova Scotia",
	"Bank of China", "Industrial & Commercial Bank of China", "Danske Bank", "Barclays", "HSBC Bank India", "Standard Chartered India", "BNP Paribas",
	"Societe Generale", "Credit Agricole Corporate and Investment Bank", "Deutsche Bank", "Bank Maybank Indonesia", "Mizuho Bank", "MUFG Bank",
	"Sumitomo Mitsui Banking Corporation", "Rabobank", "Qatar National Bank", "Sberbank", "NatWest Group", "United Overseas Bank", "FirstRand Bank",
	"Industrial Bank of Korea", "KEB Hana Bank", "Kookmin Bank", "Shinhan Bank", "Woori Bank", "Bank of Ceylon", "Handelsbanken", "UBS", "CTBC Bank",
	"Krung Thai Bank", "Abu Dhabi Commercial Bank", "Emirates NBD", "First Abu Dhabi Bank", "American Express", "Bank of America", "JPMorgan Chase",
)

# Odisha (local banks)
ODISHA_DISTRICTS_WITH_A_CENTRAL_BANK = (
	"Angul", "Aska", "Balasore-Bhadrak", "Banki", "Berhampur", "Bhawanipatna", "Bolangir", "Boudh", "Cuttack", "Keonjhar", "Khordha", "Koraput",
	"Mayurbhanj", "Nayagarh", "Sambalpur", "Sundargarh", "United Puri-Nimapara",
)

ODISHA = (
	"Odisha Grameen Bank",
	"Odisha State Co-operative Bank (OSCB)",
	*(f"{name} Central Co-operative Bank (Odisha)" for name in ODISHA_DISTRICTS_WITH_A_CENTRAL_BANK),
)

GROUPS = {
	"Public sector banks": PUBLIC_SECTOR,
	"Private sector banks": PRIVATE_SECTOR,
	"Small finance banks": SMALL_FINANCE,
	"Payments banks": PAYMENTS,
	"Local area banks": LOCAL_AREA,
	"Foreign banks": FOREIGN,
	"Odisha local banks": ODISHA,
}


def all_banks():
	"""Every bank name once, in the order of the groups."""
	return list(dict.fromkeys(name for names in GROUPS.values() for name in names))
