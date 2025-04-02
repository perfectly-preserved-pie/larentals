function reportListing(listingProps) {
    // If listingProps is a string and looks like JSON, try to parse it
    if (typeof listingProps === "string") {
        listingProps = listingProps.trim();
        if (listingProps.startsWith("{") && listingProps.endsWith("}")) {
            try {
                listingProps = JSON.parse(listingProps);
            } catch (e) {
                console.error("Error parsing listingProps:", e);
                return;
            }
        } else {
            console.error("listingProps does not appear to be valid JSON:", listingProps);
            return;
        }
    }
    // Now listingProps should be an object. Retrieve the MLS number.
    const mlsNumber = listingProps.mls_number;
    
    Swal.fire({
        // See https://sweetalert2.github.io/#configuration
        title: 'Report Listing',
        theme: 'auto',
        //width: '32rem', // Sets the popup window width
        //didOpen: (popup) => {
            // Remove horizontal scrollbar by setting overflow-x inline
        //    popup.style.overflowX = "hidden";
        //},
        html: `
          <select id="swal-input-option" class="swal2-select" style="margin-bottom:10px;width:auto;max-width:100%;">
            <option value="Wrong Location">Wrong Location</option>
            <option value="Unavailable/Sold/Rented">Unavailable/Sold/Rented</option>
            <option value="Wrong Details">Wrong Details</option>
            <option value="Incorrect Price">Incorrect Price</option>
            <option value="Other">Other</option>
          </select>
          <textarea id="swal-input-text" class="swal2-textarea" placeholder="Additional details (optional)"></textarea>
        `,
        focusConfirm: false,
        preConfirm: () => {
            return {
                option: document.getElementById('swal-input-option').value,
                text: document.getElementById('swal-input-text').value
            };
        }
    }).then((result) => {
        if (result.value) {
            fetch('/report_listing', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    mls_number: mlsNumber,
                    option: result.value.option,
                    text: result.value.text,
                    properties: listingProps
                })
            }).then(response => {
                if (response.ok) {
                    Swal.fire('Thanks!', 'Your report has been submitted.', 'success');
                } else {
                    Swal.fire('Error!', 'There was a problem reporting the listing.', 'error');
                }
            });
        }
    });
}