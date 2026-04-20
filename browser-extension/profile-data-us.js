(function () {
  window.ProfileDataUS = {
    firstNames: [
      'James', 'Olivia', 'Liam', 'Emma', 'Noah', 'Sophia', 'Elijah', 'Charlotte',
      'William', 'Amelia', 'Benjamin', 'Ava', 'Lucas', 'Mia', 'Henry', 'Evelyn',
      'Alexander', 'Harper', 'Mason', 'Luna', 'Michael', 'Camila', 'Daniel', 'Gianna',
      'Logan', 'Elizabeth', 'Jackson', 'Eleanor', 'Sebastian', 'Ella', 'Jack', 'Abigail',
      'Owen', 'Emily', 'Levi', 'Scarlett', 'Samuel', 'Grace', 'Mateo', 'Chloe',
      'David', 'Victoria', 'Joseph', 'Riley', 'John', 'Aria', 'Wyatt', 'Nora',
      'Luke', 'Hazel', 'Matthew', 'Zoey', 'Asher', 'Lily', 'Carter', 'Aurora'
    ],
    lastNames: [
      'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis',
      'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson', 'Thomas',
      'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson', 'White',
      'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson', 'Walker', 'Young',
      'Allen', 'King', 'Wright', 'Scott', 'Torres', 'Nguyen', 'Hill', 'Flores',
      'Green', 'Adams', 'Nelson', 'Baker', 'Hall', 'Rivera', 'Campbell', 'Mitchell'
    ],
    emailDomains: [
      'gmail.com', 'outlook.com', 'yahoo.com', 'icloud.com',
      'proton.me', 'examplemail.com', 'mailbox.test', 'hotmail.com'
    ],
    companyPrefixes: [
      'Blue', 'North', 'Prime', 'Liberty', 'Pioneer', 'Silver', 'Golden', 'Pacific',
      'Summit', 'Harbor', 'Granite', 'River', 'Vertex', 'Bright', 'True', 'Cedar'
    ],
    companyNouns: [
      'Labs', 'Logistics', 'Systems', 'Works', 'Partners', 'Digital', 'Networks', 'Group',
      'Holdings', 'Supply', 'Studio', 'Ventures', 'Solutions', 'Services', 'Retail', 'Dynamics'
    ],
    streetNames: [
      'Oak', 'Maple', 'Cedar', 'Pine', 'Lakeview', 'Sunset', 'Ridge', 'Elm',
      'Magnolia', 'Willow', 'Hillcrest', 'Park', 'Washington', 'Jefferson', 'Franklin', 'Lincoln',
      'Adams', 'Madison', 'Monroe', 'Jackson', 'Cherry', 'Meadow', 'Creek', 'Aspen',
      'Valley', 'River', 'Forest', 'Laurel', 'Highland', 'Chestnut', 'Dogwood', 'Hawthorne'
    ],
    streetSuffixes: ['St', 'Ave', 'Rd', 'Blvd', 'Ln', 'Dr', 'Ct', 'Way', 'Pl', 'Terrace'],
    unitPrefixes: ['Apt', 'Suite', 'Unit'],
    areaCodes: [
      '212', '213', '214', '215', '216', '303', '305', '312', '315', '404', '415', '424',
      '512', '602', '617', '646', '702', '713', '718', '720', '801', '818', '907', '917'
    ],
    states: [
      { code: 'AL', name: 'Alabama', cities: ['Birmingham', 'Montgomery', 'Huntsville'] },
      { code: 'AK', name: 'Alaska', cities: ['Anchorage', 'Fairbanks', 'Juneau'] },
      { code: 'AZ', name: 'Arizona', cities: ['Phoenix', 'Tucson', 'Mesa'] },
      { code: 'AR', name: 'Arkansas', cities: ['Little Rock', 'Fayetteville', 'Fort Smith'] },
      { code: 'CA', name: 'California', cities: ['Los Angeles', 'San Diego', 'San Jose'] },
      { code: 'CO', name: 'Colorado', cities: ['Denver', 'Colorado Springs', 'Boulder'] },
      { code: 'CT', name: 'Connecticut', cities: ['Hartford', 'New Haven', 'Stamford'] },
      { code: 'DE', name: 'Delaware', cities: ['Wilmington', 'Dover', 'Newark'] },
      { code: 'FL', name: 'Florida', cities: ['Miami', 'Orlando', 'Tampa'] },
      { code: 'GA', name: 'Georgia', cities: ['Atlanta', 'Savannah', 'Augusta'] },
      { code: 'HI', name: 'Hawaii', cities: ['Honolulu', 'Hilo', 'Kailua'] },
      { code: 'ID', name: 'Idaho', cities: ['Boise', 'Idaho Falls', 'Meridian'] },
      { code: 'IL', name: 'Illinois', cities: ['Chicago', 'Springfield', 'Naperville'] },
      { code: 'IN', name: 'Indiana', cities: ['Indianapolis', 'Fort Wayne', 'Bloomington'] },
      { code: 'IA', name: 'Iowa', cities: ['Des Moines', 'Cedar Rapids', 'Davenport'] },
      { code: 'KS', name: 'Kansas', cities: ['Wichita', 'Topeka', 'Overland Park'] },
      { code: 'KY', name: 'Kentucky', cities: ['Louisville', 'Lexington', 'Bowling Green'] },
      { code: 'LA', name: 'Louisiana', cities: ['New Orleans', 'Baton Rouge', 'Lafayette'] },
      { code: 'ME', name: 'Maine', cities: ['Portland', 'Bangor', 'Augusta'] },
      { code: 'MD', name: 'Maryland', cities: ['Baltimore', 'Annapolis', 'Frederick'] },
      { code: 'MA', name: 'Massachusetts', cities: ['Boston', 'Cambridge', 'Worcester'] },
      { code: 'MI', name: 'Michigan', cities: ['Detroit', 'Grand Rapids', 'Ann Arbor'] },
      { code: 'MN', name: 'Minnesota', cities: ['Minneapolis', 'Saint Paul', 'Rochester'] },
      { code: 'MS', name: 'Mississippi', cities: ['Jackson', 'Biloxi', 'Gulfport'] },
      { code: 'MO', name: 'Missouri', cities: ['Kansas City', 'St. Louis', 'Springfield'] },
      { code: 'MT', name: 'Montana', cities: ['Billings', 'Bozeman', 'Missoula'] },
      { code: 'NE', name: 'Nebraska', cities: ['Omaha', 'Lincoln', 'Bellevue'] },
      { code: 'NV', name: 'Nevada', cities: ['Las Vegas', 'Reno', 'Henderson'] },
      { code: 'NH', name: 'New Hampshire', cities: ['Manchester', 'Nashua', 'Concord'] },
      { code: 'NJ', name: 'New Jersey', cities: ['Newark', 'Jersey City', 'Princeton'] },
      { code: 'NM', name: 'New Mexico', cities: ['Albuquerque', 'Santa Fe', 'Las Cruces'] },
      { code: 'NY', name: 'New York', cities: ['New York', 'Buffalo', 'Albany'] },
      { code: 'NC', name: 'North Carolina', cities: ['Charlotte', 'Raleigh', 'Durham'] },
      { code: 'ND', name: 'North Dakota', cities: ['Fargo', 'Bismarck', 'Grand Forks'] },
      { code: 'OH', name: 'Ohio', cities: ['Columbus', 'Cleveland', 'Cincinnati'] },
      { code: 'OK', name: 'Oklahoma', cities: ['Oklahoma City', 'Tulsa', 'Norman'] },
      { code: 'OR', name: 'Oregon', cities: ['Portland', 'Salem', 'Eugene'] },
      { code: 'PA', name: 'Pennsylvania', cities: ['Philadelphia', 'Pittsburgh', 'Harrisburg'] },
      { code: 'RI', name: 'Rhode Island', cities: ['Providence', 'Warwick', 'Newport'] },
      { code: 'SC', name: 'South Carolina', cities: ['Charleston', 'Columbia', 'Greenville'] },
      { code: 'SD', name: 'South Dakota', cities: ['Sioux Falls', 'Rapid City', 'Pierre'] },
      { code: 'TN', name: 'Tennessee', cities: ['Nashville', 'Memphis', 'Knoxville'] },
      { code: 'TX', name: 'Texas', cities: ['Austin', 'Dallas', 'Houston'] },
      { code: 'UT', name: 'Utah', cities: ['Salt Lake City', 'Provo', 'Ogden'] },
      { code: 'VT', name: 'Vermont', cities: ['Burlington', 'Montpelier', 'Rutland'] },
      { code: 'VA', name: 'Virginia', cities: ['Richmond', 'Virginia Beach', 'Arlington'] },
      { code: 'WA', name: 'Washington', cities: ['Seattle', 'Spokane', 'Tacoma'] },
      { code: 'WV', name: 'West Virginia', cities: ['Charleston', 'Morgantown', 'Huntington'] },
      { code: 'WI', name: 'Wisconsin', cities: ['Milwaukee', 'Madison', 'Green Bay'] },
      { code: 'WY', name: 'Wyoming', cities: ['Cheyenne', 'Casper', 'Laramie'] }
    ]
  };
})();
