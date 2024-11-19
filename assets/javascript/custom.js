document.addEventListener('DOMContentLoaded', function() {
    const multiSelectDropdown = document.querySelector('.mantine-MultiSelect-dropdown');
    if (multiSelectDropdown) {
        multiSelectDropdown.addEventListener('mousedown', function(event) {
            // Prevent default focus behavior
            event.preventDefault();
            // Set focus to another element (e.g., body)
            document.body.focus();
        });
    }
});