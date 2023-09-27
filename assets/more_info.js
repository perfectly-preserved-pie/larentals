document.addEventListener('DOMContentLoaded', function() {
    var trigger = document.getElementById('more_info_trigger');
    if (trigger) {
        trigger.addEventListener('click', function() {
            var extraInfo = document.getElementById('extra_info');
            if (extraInfo.style.display === 'none') {
                extraInfo.style.display = '';
            } else {
                extraInfo.style.display = 'none';
            }
        });
    }
});