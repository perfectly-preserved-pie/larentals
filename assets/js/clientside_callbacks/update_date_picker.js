window.dash_clientside = Object.assign({}, window.dash_clientside, {
  clientside: Object.assign({}, window.dash_clientside && window.dash_clientside.clientside, {
    /**
     * Updates the date picker start_date based on the selected time range radio value.
     *
     * @param {number} selectedDays - Number of days to look back (14, 30, 90, or 0 for all time).
     * @param {string} earliestDate - The earliest available date (ISO string) from the store.
     * @returns {string} The computed start date as a YYYY-MM-DD string.
     */
    updateDatePicker: function(selectedDays, earliestDate) {
      if (!selectedDays || selectedDays === 0) {
        // "All Time" — use the earliest date from the store
        return earliestDate || null;
      }
      // Compute a date `selectedDays` days ago from today
      const now = new Date();
      now.setDate(now.getDate() - selectedDays);
      const yyyy = now.getFullYear();
      const mm = String(now.getMonth() + 1).padStart(2, '0');
      const dd = String(now.getDate()).padStart(2, '0');
      return `${yyyy}-${mm}-${dd}`;
    }
  })
});
