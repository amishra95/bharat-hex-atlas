"""District name reconciliation.

The boundary file (geoBoundaries IND ADM2, LGD 2021) carries some pre-rename spellings.
DISPLAY maps them to current official names; NFHS_ALIAS maps NFHS-6 fact-sheet names
onto boundary names where fuzzy matching fails.
"""

# (state, boundary name) -> current name shown in the app
DISPLAY = {
    ("Haryana", "Gurgaon"): "Gurugram", ("Haryana", "Mewat"): "Nuh",
    ("Karnataka", "Bangalore"): "Bengaluru Urban", ("Karnataka", "Bangalore Rural"): "Bengaluru Rural",
    ("Karnataka", "Belgaum"): "Belagavi", ("Karnataka", "Bellary"): "Ballari",
    ("Karnataka", "Bijapur"): "Vijayapura", ("Karnataka", "Gulbarga"): "Kalaburagi",
    ("Karnataka", "Mysore"): "Mysuru", ("Karnataka", "Shimoga"): "Shivamogga",
    ("Karnataka", "Tumkur"): "Tumakuru", ("Karnataka", "Chikmagalur"): "Chikkamagaluru",
    ("Uttar Pradesh", "Allahabad"): "Prayagraj", ("Uttar Pradesh", "Faizabad"): "Ayodhya",
    ("Uttar Pradesh", "Jyotiba Phule Nagar"): "Amroha", ("Uttar Pradesh", "Mahamaya Nagar"): "Hathras",
    ("Uttar Pradesh", "Kanshiram Nagar"): "Kasganj", ("Uttar Pradesh", "Sant Ravidas Nagar (Bhadohi)"): "Bhadohi",
    ("Uttar Pradesh", "Samli"): "Shamli", ("Uttar Pradesh", "Bara Banki"): "Barabanki",
    ("Uttar Pradesh", "Kheri"): "Lakhimpur Kheri", ("Uttar Pradesh", "Mahrajganj"): "Maharajganj",
    ("Uttar Pradesh", "Shrawasti"): "Shravasti",
    ("Madhya Pradesh", "Hoshangabad"): "Narmadapuram", ("Madhya Pradesh", "Agar"): "Agar Malwa",
    ("Maharashtra", "Aurangabad"): "Chhatrapati Sambhajinagar", ("Maharashtra", "Osmanabad"): "Dharashiv",
    ("Maharashtra", "Ahmadnagar"): "Ahilyanagar", ("Maharashtra", "Raigarh"): "Raigad",
    ("Maharashtra", "Bid"): "Beed", ("Maharashtra", "Buldana"): "Buldhana", ("Maharashtra", "Gondiya"): "Gondia",
    ("Telangana", "Hydrabad"): "Hyderabad", ("Telangana", "Bhadradri"): "Bhadradri Kothagudem",
    ("Telangana", "Jayashankar"): "Jayashankar Bhupalpally", ("Telangana", "Jogulamba"): "Jogulamba Gadwal",
    ("Telangana", "Komaram Bheem"): "Kumuram Bheem Asifabad", ("Telangana", "Medchal"): "Medchal-Malkajgiri",
    ("Telangana", "Warangal (U)"): "Hanumakonda", ("Telangana", "Warangal (R)"): "Warangal",
    ("Gujarat", "Batod"): "Botad", ("Gujarat", "Dohad"): "Dahod", ("Gujarat", "Mahesana"): "Mehsana",
    ("Gujarat", "Kachchh"): "Kutch", ("Gujarat", "Panch Mahals"): "Panchmahal",
    ("Gujarat", "Banas Kantha"): "Banaskantha", ("Gujarat", "Sabar Kantha"): "Sabarkantha",
    ("Gujarat", "Ahmadabad"): "Ahmedabad",
    ("Andhra Pradesh", "Kadapa(YSR)"): "YSR Kadapa", ("Andhra Pradesh", "Sri Potti Sriramulu Nellore"): "Nellore",
    ("Punjab", "Muktsar"): "Sri Muktsar Sahib", ("Punjab", "Sahibzada Ajit Singh Nagar"): "SAS Nagar (Mohali)",
    ("Punjab", "Shahid Bhagat Singh Nagar"): "SBS Nagar",
    ("West Bengal", "Koch Bihar"): "Cooch Behar", ("West Bengal", "Haora"): "Howrah", ("West Bengal", "Hugli"): "Hooghly",
    ("West Bengal", "Darjiling"): "Darjeeling", ("West Bengal", "Puruliya"): "Purulia", ("West Bengal", "Maldah"): "Malda",
    ("West Bengal", "Barddhaman"): "Purba Bardhaman", ("West Bengal", "North Twenty Four Parganas"): "North 24 Parganas",
    ("West Bengal", "South Twenty Four Parganas"): "South 24 Parganas",
    ("Rajasthan", "Dhaulpur"): "Dholpur", ("Rajasthan", "Jhunjhunun"): "Jhunjhunu", ("Rajasthan", "Jalor"): "Jalore",
    ("Rajasthan", "Chittaurgarh"): "Chittorgarh", ("Rajasthan", "Ganganagar"): "Sri Ganganagar",
    ("Uttarakhand", "Garhwal"): "Pauri Garhwal", ("Uttarakhand", "Hardwar"): "Haridwar",
    ("Jammu & Kashmir", "Shupiyan"): "Shopian", ("Jammu & Kashmir", "Baramula"): "Baramulla",
    ("Jammu & Kashmir", "Badgam"): "Budgam", ("Jammu & Kashmir", "Punch"): "Poonch",
    ("Ladakh", "Leh(Ladakh)"): "Leh", ("Ladakh", "DATA NOT AVAILABLE"): "Gilgit-Baltistan (Pakistan-administered)",
    ("Odisha", "Anugul"): "Angul", ("Odisha", "Baleshwar"): "Balasore", ("Odisha", "Debagarh"): "Deogarh",
    ("Odisha", "Jajapur"): "Jajpur", ("Odisha", "Kendujhar"): "Keonjhar", ("Odisha", "Subarnapur"): "Sonepur",
    ("Odisha", "Baudh"): "Boudh", ("Chhattisgarh", "Kabeerdham"): "Kabirdham",
    ("Chhattisgarh", "Dakshin Bastar Dantewada"): "Dantewada", ("Chhattisgarh", "Uttar Bastar Kanker"): "Kanker",
    ("Tamil Nadu", "Thiruvallur"): "Tiruvallur", ("Tamil Nadu", "Kancheepuram"): "Kanchipuram",
    ("Tamil Nadu", "Thoothukkudi"): "Thoothukudi", ("Tamil Nadu", "Chengalputtu"): "Chengalpattu",
}

# (state, NFHS-6 name) -> boundary name
NFHS_ALIAS = {
    ("Andhra Pradesh", "Y.S.R."): "Kadapa(YSR)", ("Chhattisgarh", "Dantewada"): "Dakshin Bastar Dantewada",
    ("Gujarat", "Botad"): "Batod", ("Gujarat", "Dahod"): "Dohad",
    ("Haryana", "Gurugram"): "Gurgaon", ("Haryana", "Nuh"): "Mewat",
    ("Jammu & Kashmir", "Shopian"): "Shupiyan",
    ("Karnataka", "Belagavi"): "Belgaum", ("Karnataka", "Bengaluru Rural"): "Bangalore Rural",
    ("Karnataka", "Bengaluru Urban"): "Bangalore", ("Karnataka", "Kalaburagi"): "Gulbarga",
    ("Karnataka", "Mysuru"): "Mysore", ("Karnataka", "Vijayapura"): "Bijapur",
    ("Ladakh", "Leh Ladakh"): "Leh(Ladakh)", ("Madhya Pradesh", "Agar Malwa"): "Agar",
    ("Maharashtra", "Raigad"): "Raigarh", ("Odisha", "Boudh"): "Baudh", ("Odisha", "Sonepur"): "Subarnapur",
    ("Puducherry", "Pondicherry"): "Puducherry", ("Puducherry", "Yanam"): "Yanam",
    ("Punjab", "Sri Muktsar Sahib"): "Muktsar", ("Rajasthan", "Dholpur"): "Dhaulpur",
    ("Tamil Nadu", "Tuticorin"): "Thoothukkudi",
    ("Telangana", "Bhadradri Kothagudem"): "Bhadradri", ("Telangana", "Hanumakonda"): "Warangal (U)",
    ("Telangana", "Jayashankar Bhupalapally"): "Jayashankar", ("Telangana", "Jogulamba Gadwal"): "Jogulamba",
    ("Telangana", "Kumuram Bheem Asifabad"): "Komaram Bheem", ("Telangana", "Medchal Malkajgiri"): "Medchal",
    ("Uttar Pradesh", "Amroha"): "Jyotiba Phule Nagar", ("Uttar Pradesh", "Ayodhya"): "Faizabad",
    ("Uttar Pradesh", "Bhadohi"): "Sant Ravidas Nagar (Bhadohi)", ("Uttar Pradesh", "Hathras"): "Mahamaya Nagar",
    ("Uttar Pradesh", "Kasganj"): "Kanshiram Nagar", ("Uttar Pradesh", "Prayagraj"): "Allahabad",
    ("Uttarakhand", "Pauri Garhwal"): "Garhwal",
    ("West Bengal", "Cooch Behar"): "Koch Bihar", ("West Bengal", "Howrah"): "Haora",
    ("West Bengal", "Purba Bardhaman"): "Barddhaman",
}

# boundary districts whose spatial state assignment is wrong (enclaves)
STATE_FIX = {"Yanam": "Puducherry"}
CLAIMED = {("Ladakh", "DATA NOT AVAILABLE")}
