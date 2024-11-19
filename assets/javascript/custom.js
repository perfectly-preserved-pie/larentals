document.addEventListener('DOMContentLoaded', function() {
    const multiSelectDropdown = document.querySelector('.mantine-MultiSelect-dropdown');
    if (multiSelectDropdown) {
        multiSelectDropdown.addEventListener('focus', function(event) {
            event.preventDefault();
            event.stopPropagation();
        });
    }
});