document.addEventListener('DOMContentLoaded', function() {
    const multiSelectInput = document.querySelector('.mantine-MultiSelect-input');
    if (multiSelectInput) {
        multiSelectInput.addEventListener('focus', function(event) {
            event.preventDefault();
            event.stopPropagation();
        });
    }
});