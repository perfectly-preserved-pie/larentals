const common = {
  priceRange: [0, null], bedroomsRange: [0, 12], bedroomsUpperBound: 12,
  bathroomsRange: [0, 12], bathroomsUpperBound: 12,
  sqftRange: [0, null], sqftMissing: true, ppsqftRange: [0, null], ppsqftMissing: true,
  yearRange: [0, 2026], yearMissing: true, subtypes: [],
  dateStart: "2020-01-01", dateEnd: "2026-10-14", dateMissing: true,
  downloadRange: [0, 10000], uploadRange: [0, 10000], ispMissing: true,
  requiredAmenities: [], zipBoundary: {},
};

/**
 * Build listings with an independent rejection rule for each filter group.
 * Seven anchors survive every group, keeping percentile checks meaningful even
 * when all groups are active; each additional listing fails exactly one group.
 * @param {"lease"|"buy"} key Listing mode whose filters should be exercised.
 * @returns {object} Baseline state, restrictive group patches and source listings.
 */
function matrix(key) {
  const lease = key === "lease";
  const base = {
    ...common, pets: "any", parkingRange: [0, 12], parkingUpperBound: 12, parkingMissing: true,
    terms: [], termsMissing: true, furnished: [], furnishedMissing: true,
    securityRange: [0, null], securityMissing: true,
    petDepositRange: [0, null], petDepositMissing: true,
    keyDepositRange: [0, null], keyDepositMissing: true,
    otherDepositRange: [0, null], otherDepositMissing: true,
    laundry: [], laundryMissing: true, rentControl: "any",
    lotSizeRange: [0, null], lotSizeMissing: true,
    hoaRange: [0, null], hoaMissing: true, hoaFrequency: [],
  };
  const otherPageFields = lease ? ["lotSizeRange", "lotSizeMissing", "hoaRange", "hoaMissing", "hoaFrequency"]
    : ["pets", "parkingRange", "parkingUpperBound", "parkingMissing", "terms", "termsMissing", "furnished",
      "furnishedMissing", "securityRange", "securityMissing", "petDepositRange", "petDepositMissing",
      "keyDepositRange", "keyDepositMissing", "otherDepositRange", "otherDepositMissing", "laundry", "laundryMissing", "rentControl"];
  for (const name of otherPageFields) delete base[name];
  // Each negative listing fails exactly one group when that group is active.
  // This gives an independent AND oracle for every possible subset.
  const groups = [
    ["location", { zipBoundary: { zip_codes: ["90012"] } }, { zip_code: "90210" }],
    ["price", { priceRange: lease ? [1500, 4500] : [300000, 1000000] }, { list_price: lease ? 5000 : 1100000 }],
    ["bedrooms", { bedroomsRange: [2, 12] }, { bedrooms: 1 }],
    ["bathrooms", { bathroomsRange: [2, 12] }, { total_bathrooms: 1 }],
    ["amenities", lease ? { requiredAmenities: ["has_ac", "has_dishwasher"], laundry: ["In Unit"], laundryMissing: false }
      : { requiredAmenities: ["has_ac", "has_dishwasher"] }, { has_ac: "No" }],
    ["sqft", { sqftRange: [1000, 2000], sqftMissing: false }, { sqft: 500 }],
    ["ppsqft", { ppsqftRange: [1, 1000], ppsqftMissing: false }, { ppsqft: 0.5 }],
    ["year", { yearRange: [1990, 2026], yearMissing: false }, { year_built: 1980 }],
    ["subtypes", { subtypes: ["group:single_family"] }, { subtype: "Apartment" }],
    ["listedDate", { dateStart: "2026-10-01", dateEnd: "2026-10-14", dateMissing: false }, { listed_date: "2026-09-01" }],
    ["isp", { downloadRange: [100, 10000], uploadRange: [100, 10000], ispMissing: false }, { best_dn: 50 }],
  ];
  if (lease) groups.push(
    ["pets", { pets: "allowed" }, { pet_policy: "No" }],
    ["parking", { parkingRange: [1, 12], parkingMissing: false }, { parking_spaces: 0 }],
    ["terms", { terms: ["12 Months"], termsMissing: false }, { terms: "Month To Month" }],
    ["furnished", { furnished: ["Unfurnished"], furnishedMissing: false }, { furnished: "Furnished" }],
    ["deposits", { securityRange: [0, 3000], petDepositRange: [0, 500], keyDepositRange: [0, 100],
      otherDepositRange: [0, 100], securityMissing: false, petDepositMissing: false,
      keyDepositMissing: false, otherDepositMissing: false }, { security_deposit: 4000 }],
    ["rentControl", { rentControl: "rso" }, { rent_control_status: "not_rso" }],
  );
  else groups.push(
    ["lotSize", { lotSizeRange: [1000, 10000], lotSizeMissing: false }, { lot_size: 500 }],
    ["hoa", { hoaRange: [0, 1000], hoaMissing: false }, { hoa_fee: 1500 }],
    ["hoaFrequency", { hoaFrequency: ["Monthly"] }, { hoa_fee_frequency: "Annually" }],
  );
  const props = {
    list_price: lease ? 3000 : 700000, bedrooms: 3, total_bathrooms: 2,
    sqft: 1500, ppsqft: 2, year_built: 2000, subtype: "Single Family Residence",
    listed_date: "2026-10-10", best_dn: 1000, best_up: 1000, zip_code: "90012",
    has_ac: "Yes", has_dishwasher: "Yes", laundry_category: "In Unit",
    pet_policy: "Yes", parking_spaces: 2, terms: "12 Months", furnished: "Unfurnished",
    security_deposit: 2000, pet_deposit: 200, key_deposit: 50, other_deposit: 50,
    rent_control_status: "rso", lot_size: 5000, hoa_fee: 500, hoa_fee_frequency: "Monthly",
  };
  const features = [];
  function add(id, patch, excludedBy = -1) {
    const i = features.length;
    features.push({ type: "Feature", geometry: { type: "Point", coordinates:
      i < 4 ? [-118.25 + i * 0.005, 34.05] : [-118.65 + (i % 6) * 0.15, 33.8 + Math.floor(i / 6) * 0.15] },
    properties: { ...props, ...patch, mls_number: id, full_street_address: id }, excludedBy });
  }
  for (let i = 0; i < 7; i++) add(`anchor-${i}`, { list_price: lease ? 1600 + i * 450 : 350000 + i * 100000 });
  groups.forEach(([name, , patch], i) => add(`reject-${name}`, patch, i));
  return { base, groups, source: { type: "FeatureCollection", features } };
}

/**
 * Activate the filter groups selected by a subset mask.
 * Build a fresh state so adjacent combinations cannot retain earlier restrictions.
 * @param {object} base Unrestricted filter state.
 * @param {Array} groups Named filter patches from the fixture matrix.
 * @param {number} mask One bit per active group.
 * @returns {object} Filter state for this combination.
 */
function stateFor(base, groups, mask) {
  const state = { ...base };
  groups.forEach(([, patch], i) => { if (mask & (2 ** i)) Object.assign(state, patch); });
  return state;
}

module.exports = { matrix, stateFor };
