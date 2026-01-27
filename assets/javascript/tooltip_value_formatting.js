// https://community.plotly.com/t/dash-2-15-0-released-slider-tooltip-styling-setting-allowed-axes-range-more-page-routing-inputs/82204#rangeslider-transforming-tooltip-values-4

/**
 * Formats a number as a currency string with a dollar sign and thousands separators.
 * Assumes the default locale is 'en-US' for currency formatting.
 * @param {number} value - The numeric value to format as currency.
 * @returns {string} The formatted currency string.
 */
window.dccFunctions = window.dccFunctions || {};
window.dccFunctions.formatCurrency = function(value) {
  if (typeof value !== 'number') {
    console.error('formatCurrency expects a number as the input');
    return value; // Return the input as is
  }

  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  });
}

/**
 * Formats a number as a square footage string with "sq. ft" appended.
 * 
 * @param {number} value - The numerical value to format.
 * @returns {string} The formatted square footage string with "sq. ft" appended.
 */
window.dccFunctions = window.dccFunctions || {};
window.dccFunctions.formatSqFt = function(value) {
  // Convert the number to a fixed-point notation, with 0 decimal places
  // Then replace every non-boundary character before a group of 3 digits with a comma
  // Finally, append " sq. ft" to the string
  return value.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ",") + ' sq. ft';
}

/**
 * Formats ISP speeds in Mbps/Gbps depending on magnitude.
 *
 * @param {number} value - The speed in Mbps.
 * @returns {string} The formatted speed string.
 */
window.dccFunctions = window.dccFunctions || {};
window.dccFunctions.formatIspSpeed = function(value) {
  const ISP_SPEED_EPSILON = 1e-9;
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    console.error('formatIspSpeed expects a finite number as the input:', value);
    return value;
  }
  if (value >= 1000) {
    const gbps = value / 1000;
    const rounded = Math.abs(gbps - Math.round(gbps)) < ISP_SPEED_EPSILON ? Math.round(gbps) : gbps.toFixed(1);
    return `${rounded} Gbps`;
  }
  return `${Math.round(value)} Mbps`;
}
