"""Reviewed corrections for inaccurate ZIPs in recurring MLS source reports."""

from __future__ import annotations

import pandas as pd

from functions.listing_report_utils import normalize_mls_number


ZIP_OVERRIDES = {
    ("buy", "TR26010924MR"): "91732",  # 11547 Lower Azusa Rd, El Monte
    ("buy", "SR26018258MR"): "91706",  # 4306 Baldwin Park Blvd
    ("lease", "WS26121911MR"): "91755",  # 130 New Ave, unit 5
    ("lease", "WS26115741MR"): "91755",  # 130 New Ave, unit 6
    ("lease", "SR25037140MR"): "91403",  # 4383 Sepulveda Blvd, unit 401
    ("lease", "SR26114937MR"): "91351",  # issue 349 reviewed address
    ("lease", "SB25209687MR"): "90250",  # issue 349 reviewed address
    ("lease", "BB26036504MR"): "91042",  # issue 349 reviewed address
    ("lease", "BB26036751MR"): "91042",  # issue 349 reviewed address
    ("lease", "26873517"): "90036",  # issue 349 reviewed address
    ("lease", "CV26175754MR"): "91204",  # issue 349 reviewed address
    ("lease", "SB26090596MR"): "90242",  # issue 349 reviewed address
    ("buy", "CV26196389MR"): "91767",  # issue 349 reviewed address
    ("buy", "P1-28190PF"): "91355",  # issue 349 reviewed address
    ("lease", "SR26008965MR"): "91342",  # 12867 1/2 Norris Ave, Sylmar
    ("lease", "SR26049795MR"): "90044",  # 932 W 74th St, Los Angeles
    ("lease", "26655135"): "91324",  # 18558 Roscoe Blvd, Northridge
    ('lease', '41080135CC'): '94596',  # issue 349 source review
    ('lease', 'CV23042565'): '91767',  # issue 349 source review
    ('lease', 'CV23079669'): '91767',  # issue 349 source review
    ('lease', 'CV23081475'): '91767',  # issue 349 source review
    ('lease', 'CV23162640'): '91767',  # issue 349 source review
    ('lease', 'CV23167483'): '91767',  # issue 349 source review
    ('lease', 'CV23181488'): '91767',  # issue 349 source review
    ('lease', 'CV23204338'): '91767',  # issue 349 source review
    ('lease', 'CV23204950'): '91767',  # issue 349 source review
    ('lease', 'CV24002830'): '91767',  # issue 349 source review
    ('lease', 'CV24002964'): '91767',  # issue 349 source review
    ('lease', 'CV24015078'): '91767',  # issue 349 source review
    ('lease', 'CV24132011'): '91767',  # issue 349 source review
    ('lease', 'CV24140332'): '91767',  # issue 349 source review
    ('lease', 'DW26178487MR'): '90660',  # issue 349 source review
    ('lease', 'PW22234596'): '90605',  # issue 349 source review
    ('lease', 'SB25002589MR'): '90802',  # issue 349 source review
    ('lease', 'SB25052003MR'): '90802',  # issue 349 source review
    ('lease', 'SB25264812MR'): '90254',  # issue 349 source review
    ('lease', 'SB26179373MR'): '90744',  # issue 349 source review
    ('lease', 'SR25273029MR'): '90277',  # issue 349 source review
    ('lease', 'TR26055123MR'): '91732',  # issue 349 source review
    ('buy', 'SR26200295MR'): '93535',  # issue 349 source review
    ('lease', 'CV25002817MR'): '91767',  # issue 349 source review
    ('lease', 'P1-28339PF'): '91107',  # issue 349 source review
    ("buy", "SR26145166MR"): "93536",
    ("lease", "TR26127636MR"): "90640",
    ("lease", "SR25020807MR"): "93551",
    ('buy', 'SW26154406MR'): '93535',
    ('buy', 'SW26155342MR'): '93535',
    ('buy', 'SW26155366MR'): '93535',
    ('buy', 'SW26155402MR'): '93535',
    ('buy', 'SW26170206MR'): '93535',
    ('buy', 'SW26170246MR'): '93535',
    ('buy', 'SW26184020MR'): '93535',
    ('buy', 'SW26192618MR'): '93535',
    ('lease', 'SR25220571MR'): '91316',
    ('lease', 'SR25232661MR'): '91316',
    ('lease', 'SR25104175MR'): '91356',
    ('lease', 'SR25161250MR'): '91356',
    ('lease', 'P1-27317PF'): '91020',
    ('buy', 'DW26140100MR'): '90001',
    ('lease', '26881059'): '91201',
    ('buy', 'PW26127420MR'): '90241',
    ('lease', 'SW25256907MR'): '91506',
}


CITY_OVERRIDES = {
    ("lease", "SR25037140MR"): "SHERMAN OAKS",
    ("buy", "IG26164136MR"): "PACOIMA",
    ("lease", "TR25271617MR"): "MONTEREY PARK",
    ("lease", "DW26178487MR"): "PICO RIVERA",
    ("lease", "PW23217874"): "LOS ALAMITOS",
    ("lease", "41080135CC"): "WALNUT CREEK",
    ("lease", "SR25020807MR"): "PALMDALE",
}


STREET_OVERRIDES = {
    ("buy", "IG26164136MR"): "10251 Angel Ln",
    ("buy", "OC26161534MR"): "1507 Mission Ln",
    ("lease", "SR26163104MR"): "Sherman Way",
    ("lease", "SR26022546MR"): "Brand Blvd",
    ("lease", "TR26138619MR"): "Normal Ave  #6",
    ("buy", "SB26167203MR"): "8832 Prince Ave",
    ("buy", "PW26177832MR"): "10400 Mary Ave",
    ("lease", "PW22234596"): "Christine Dr Apt D",
    ("lease", "P1-28339PF"): "S Parkwood Ave",
    ('buy', 'SR26074697MR'): '2718 E Avenue S',
    ('buy', 'CV26155023MR'): '7040 3rd Ave',
    ('buy', 'DW26193684MR'): '6534 4th Ave',
    ('buy', 'PW26100150MR'): '6502 4th Ave',
    ('buy', 'SR26191008MR'): '2928 Virginia Rd',
    ('lease', 'PW26171272MR'): 'Virginia Rd  #1/2',
    ('lease', 'TR26127636MR'): 'Mullberry Pl',
    ('lease', 'SR26178157MR'): '32nd St W  #34',
    ('lease', 'SR26140541MR'): '25th St W',
    ('lease', 'SR25256235MR'): '25th St W  #B7',
    ('lease', 'SR26096168MR'): '30th St W',
    ('lease', 'SR26192406MR'): '27th St W',
    ('lease', 'SR25020807MR'): 'W Avenue N  #F',
    ('lease', 'SR25144888MR'): 'W Avenue N  #F',
    ('buy', 'TR26201512MR'): '5931 5th Ave',
    ('buy', 'DW26193178MR'): '5939 5th Ave',
    ('lease', 'PW26143877MR'): 'S Normandie Ave',
    ('lease', 'SR26177383MR'): '23rd St W',
    ('lease', 'SB25183879MR'): 'W Avenue J-14',
    ('lease', 'SR25220571MR'): 'Yarmouth Ave',
    ('lease', 'SR25232661MR'): 'Yarmouth Ave',
    ('lease', 'SR25104175MR'): 'Beckford Ave',
    ('lease', 'SR25161250MR'): 'Beckford Ave',
    ('lease', '26870213'): 'Western Ave  #2',
    ('buy', 'DW26174427MR'): '7828 Bell Ave',
    ('lease', 'PW26196814MR'): 'Pacific Ave  #109',
    ('buy', 'DW26168124MR'): '815 Pacific Ave',
    ('lease', 'SB26201369MR'): 'Burbank Blvd #108',
    ('lease', 'P1-27317PF'): 'Montrose Ave #10',
    ('lease', 'SR26055342MR'): 'W Avenue L-8 #20',
    ('buy', 'SR26194160MR'): '45115 18th St W',
    ('buy', 'SR26167962MR'): '44632 17th St W',
    ('buy', 'PW26156617MR'): '210 Grand Ave #102',
    ('buy', 'DW26140100MR'): '1947 E 74th St',
    ('lease', '26881059'): 'W Glenoaks Blvd #D',
    ('buy', 'PW26127420MR'): '7033 Stewart and Gray Rd #24',
    ('buy', 'PW26137202MR'): '2805 E 3rd St #6',
    ("lease", 'SB25089948MR'): 'W 104th St',
    ("lease", 'PW26200312MR'): 'E 3rd St  #201',
    ("lease", 'SB25232990MR'): 'Fashion Ave  #A',
    ("lease", 'SB25268657MR'): 'Fashion Ave  #A',
    ("lease", 'SR26024788MR'): 'Seco Canyon Rd  #156',
    ("lease", 'SW25256907MR'): 'W Angeleno Ave  #C',
}


STREET_NUMBER_OVERRIDES = {
    ("lease", "P1-28339PF"): "31",
    ("lease", "SR25020807MR"): "3112",
}


def apply_reviewed_location_overrides(df: pd.DataFrame, listing_type: str) -> pd.DataFrame:
    """Apply reviewed source ZIP, city, street, and number corrections."""
    corrections = {
        mls: zip_code
        for (kind, mls), zip_code in ZIP_OVERRIDES.items()
        if kind == listing_type
    }
    corrected = df["mls_number"].apply(normalize_mls_number).map(corrections)
    if corrected.notna().any():
        df["zip_code"] = df["zip_code"].astype("object")
        df.loc[corrected.notna(), "zip_code"] = corrected[corrected.notna()]
    city_corrections = {
        mls: city
        for (kind, mls), city in CITY_OVERRIDES.items()
        if kind == listing_type
    }
    resolved_cities = df["mls_number"].apply(normalize_mls_number).map(city_corrections)
    if resolved_cities.notna().any():
        df["city"] = df["city"].astype("object")
        df.loc[resolved_cities.notna(), "city"] = resolved_cities[resolved_cities.notna()]
    street_corrections = {
        mls: street
        for (kind, mls), street in STREET_OVERRIDES.items()
        if kind == listing_type
    }
    street_column = "street_address" if listing_type == "buy" else "street_name"
    resolved_streets = df["mls_number"].apply(normalize_mls_number).map(street_corrections)
    if resolved_streets.notna().any():
        df[street_column] = df[street_column].astype("object")
        df.loc[resolved_streets.notna(), street_column] = resolved_streets[resolved_streets.notna()]
    number_corrections = {
        mls: number
        for (kind, mls), number in STREET_NUMBER_OVERRIDES.items()
        if kind == listing_type
    }
    resolved_numbers = df["mls_number"].apply(normalize_mls_number).map(number_corrections)
    if resolved_numbers.notna().any():
        df["street_number"] = df["street_number"].astype("object")
        df.loc[resolved_numbers.notna(), "street_number"] = resolved_numbers[resolved_numbers.notna()]
    return df
