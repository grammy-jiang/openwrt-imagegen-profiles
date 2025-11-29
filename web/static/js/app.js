/* OpenWrt Image Generator Web GUI - app.js */

/**
 * Copy text to clipboard with visual feedback
 * @param {string} text - Text to copy
 * @param {HTMLElement} btn - Button element for feedback
 */
function copyToClipboard(text, btn) {
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(function() {
            showCopyFeedback(btn, true);
        }).catch(function() {
            fallbackCopyToClipboard(text, btn);
        });
    } else {
        fallbackCopyToClipboard(text, btn);
    }
}

/**
 * Fallback copy method for older browsers
 * @param {string} text - Text to copy
 * @param {HTMLElement} btn - Button element for feedback
 */
function fallbackCopyToClipboard(text, btn) {
    var textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.left = "-999999px";
    textArea.style.top = "-999999px";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    
    try {
        // Note: document.execCommand('copy') is deprecated but used here as a
        // fallback for older browsers that don't support the Clipboard API.
        // Modern browsers will use navigator.clipboard.writeText() instead.
        var successful = document.execCommand('copy');
        showCopyFeedback(btn, successful);
    } catch (err) {
        showCopyFeedback(btn, false);
    }
    
    document.body.removeChild(textArea);
}

/**
 * Show visual feedback after copy attempt
 * @param {HTMLElement} btn - Button element
 * @param {boolean} success - Whether copy was successful
 */
function showCopyFeedback(btn, success) {
    var originalText = btn.textContent;
    btn.textContent = success ? '✓ Copied!' : '✗ Failed';
    btn.disabled = true;
    
    setTimeout(function() {
        btn.textContent = originalText;
        btn.disabled = false;
    }, 2000);
}

/**
 * Poll a URL for status updates
 * @param {string} url - URL to poll
 * @param {function} callback - Callback function receiving response data
 * @param {number} interval - Poll interval in milliseconds
 * @param {function} stopCondition - Function returning true when polling should stop
 * @returns {number} - Interval ID for clearing
 */
function pollStatus(url, callback, interval, stopCondition) {
    interval = interval || 5000;
    
    function poll() {
        fetch(url, {
            headers: {
                'Accept': 'text/html'
            }
        })
        .then(function(response) {
            if (!response.ok) {
                throw new Error('Poll request failed');
            }
            return response.text();
        })
        .then(function(data) {
            callback(data);
            if (stopCondition && stopCondition(data)) {
                clearInterval(intervalId);
            }
        })
        .catch(function(error) {
            console.error('Polling error:', error);
        });
    }
    
    poll(); // Initial poll
    var intervalId = setInterval(poll, interval);
    return intervalId;
}

/**
 * Confirm a dangerous action
 * @param {string} message - Confirmation message
 * @returns {boolean} - Whether user confirmed
 */
function confirmAction(message) {
    return window.confirm(message);
}

/**
 * Format bytes to human readable string
 * @param {number} bytes - Number of bytes
 * @returns {string} - Formatted string
 */
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    var k = 1024;
    var sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    var i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Format a datetime string to local format
 * @param {string} isoString - ISO 8601 datetime string
 * @returns {string} - Formatted local datetime
 */
function formatDateTime(isoString) {
    if (!isoString) return '-';
    var date = new Date(isoString);
    return date.toLocaleString();
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Add click handlers for copy buttons
    document.querySelectorAll('[data-copy]').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var text = this.getAttribute('data-copy');
            copyToClipboard(text, this);
        });
    });
    
    // Auto-submit filter forms on change (optional enhancement)
    document.querySelectorAll('.filter-bar select').forEach(function(select) {
        select.addEventListener('change', function() {
            if (this.closest('form').classList.contains('auto-submit')) {
                this.closest('form').submit();
            }
        });
    });
});
