// server/static/js/script_task.js
document.addEventListener('DOMContentLoaded', function() {
    'use strict';

    // --- DOM Element Caching ---
    const sidebarNavLinks = document.querySelectorAll('.sidebar-nav a.nav-link');
    const adminMenuButton = document.getElementById('adminMenuButton');
    const adminDropdown = document.getElementById('adminDropdown'); // This is the UL/DIV for the dropdown items
    const helpButton = document.getElementById('helpButton');
    const sidebarOnlineCountEl = document.getElementById('sidebarOnlineCount');
    const sidebarEmployeeListEl = document.getElementById('sidebarEmployeeList');
    const apiEndpointsDiv = document.getElementById('apiEndpoints');

    // --- Configuration ---
    const ACTIVE_EMPLOYEE_POLL_INTERVAL = 30000; // 30 seconds
    let SCRIPT_ROOT = ""; // Initialize SCRIPT_ROOT
    if (typeof window.SCRIPT_ROOT !== 'undefined') { // Get SCRIPT_ROOT if passed from Flask template
        SCRIPT_ROOT = window.SCRIPT_ROOT;
    } else if (apiEndpointsDiv && apiEndpointsDiv.dataset.scriptRoot) { // Fallback to data attribute
        SCRIPT_ROOT = apiEndpointsDiv.dataset.scriptRoot;
    }


    // --- Helper Functions ---
    function getApiUrl(dataAttributeName) {
        if (apiEndpointsDiv && apiEndpointsDiv.dataset[dataAttributeName]) {
            return SCRIPT_ROOT + apiEndpointsDiv.dataset[dataAttributeName]; // Prepend SCRIPT_ROOT
        }
        return null;
    }

    // --- Sidebar Active State ---
    function setActiveSidebarLink() {
        if (!sidebarNavLinks.length) return;

        const currentPath = window.location.pathname;
        const normalizedCurrentPath = currentPath.replace(/\/$/, ""); // Remove trailing slash for comparison

        let mostSpecificMatch = null;
        let longestMatchLength = 0;

        sidebarNavLinks.forEach(link => {
            let linkHref = link.getAttribute('href');
            if (!linkHref) return;
            
            // Make href relative if it's absolute to current domain
            if (linkHref.startsWith(window.location.origin)) {
                linkHref = linkHref.substring(window.location.origin.length);
            }
            // Prepend SCRIPT_ROOT if href is relative and SCRIPT_ROOT exists
            if (!linkHref.startsWith('/') && SCRIPT_ROOT) {
                 linkHref = SCRIPT_ROOT + '/' + linkHref;
            } else if (!linkHref.startsWith(SCRIPT_ROOT) && SCRIPT_ROOT) {
                 linkHref = SCRIPT_ROOT + linkHref;
            }

            const normalizedLinkHref = linkHref.replace(/\/$/, "");

            link.classList.remove('active'); // Clear previous active states

            // Exact match is highest priority
            if (normalizedCurrentPath === normalizedLinkHref) {
                mostSpecificMatch = link;
                longestMatchLength = normalizedLinkHref.length; // For specificity
            } 
            // Parent path activation (if no exact match found yet or current match is less specific)
            else if (normalizedLinkHref !== SCRIPT_ROOT && // Avoid matching root path "/" as parent for everything
                       normalizedCurrentPath.startsWith(normalizedLinkHref + '/') && 
                       normalizedLinkHref.length > longestMatchLength && !mostSpecificMatch) {
                mostSpecificMatch = link; // Tentatively set parent as active
                // Don't update longestMatchLength here, exact match is preferred
            }
        });
        
        if (mostSpecificMatch) {
            mostSpecificMatch.classList.add('active');
        } else if (normalizedCurrentPath === SCRIPT_ROOT || normalizedCurrentPath === SCRIPT_ROOT + '/') {
            // Fallback to dashboard if on root path and no other match
            const dashboardLink = document.querySelector('.sidebar-nav a[href*="/dashboard"]');
            if(dashboardLink) dashboardLink.classList.add('active');
        }
    }

    // --- Admin Dropdown Menu (using Bootstrap 5 JS API) ---
    function initializeAdminDropdown() {
        if (!adminMenuButton || !adminDropdown) return;

        // Bootstrap 5 Dropdown initialization
        let bsDropdownInstance = null;
        if (typeof bootstrap !== 'undefined' && bootstrap.Dropdown) {
            bsDropdownInstance = bootstrap.Dropdown.getInstance(adminMenuButton);
            if (!bsDropdownInstance) {
                bsDropdownInstance = new bootstrap.Dropdown(adminMenuButton);
            }
        }

        adminMenuButton.addEventListener('click', function(e) {
            // Bootstrap's data-bs-toggle="dropdown" should handle this automatically.
            // This event listener is more for custom actions if needed.
            // e.stopPropagation(); // Usually not needed with Bootstrap's handling
        });
        
        // Clicking dropdown items should navigate (href) and close the dropdown
        adminDropdown.querySelectorAll('.dropdown-item').forEach(item => {
            item.addEventListener('click', function() {
                if (bsDropdownInstance) {
                    bsDropdownInstance.hide();
                }
            });
        });
    }

    // --- Help Button ---
    function initializeHelpButton() {
        if (!helpButton) return;
        helpButton.addEventListener('click', function() {
            alert('Help & Support (Feature under development)');
        });
    }

    // --- Employees Online Polling ---
    function fetchActiveEmployeesSidebar() {
        if (!sidebarEmployeeListEl || !sidebarOnlineCountEl) return;

        const activeEmployeesUrl = getApiUrl('activeEmployeesUrl');
        const userEditUrlBase = getApiUrl('userEditUrlBase');

        if (!activeEmployeesUrl || !userEditUrlBase) {
            if (sidebarEmployeeListEl.textContent.includes("Loading...")) {
                sidebarEmployeeListEl.innerHTML = '<li class="text-muted small" style="padding-left:0;">API config error.</li>';
                sidebarOnlineCountEl.textContent = 'X';
            }
            return;
        }

        fetch(activeEmployeesUrl)
            .then(response => {
                if (!response.ok) {
                    if (sidebarOnlineCountEl.textContent !== '?') sidebarOnlineCountEl.textContent = '?';
                    return null;
                }
                return response.json();
            })
            .then(data => {
                if (!sidebarEmployeeListEl || !sidebarOnlineCountEl) return;

                if (data && Array.isArray(data)) {
                    sidebarEmployeeListEl.innerHTML = ''; 
                    if (data.length > 0) {
                        sidebarOnlineCountEl.textContent = data.length;
                        data.forEach(emp => {
                            const listItem = document.createElement('li');
                            let userEditUrl = userEditUrlBase.replace('EMP_ID_PLACEHOLDER', emp._id || '');
                            
                            const displayName = emp.display_name || emp.employee_id || 'Unnamed';
                            const truncatedName = displayName.length > 18 ? displayName.substring(0, 16) + '...' : displayName;

                            listItem.innerHTML = `
                                <span class="online-dot"></span>
                                <a href="${userEditUrl}" 
                                   title="${displayName} (ID: ${emp.employee_id || 'N/A'})">
                                   ${truncatedName}
                                </a>`;
                            sidebarEmployeeListEl.appendChild(listItem);
                        });
                    } else {
                        sidebarOnlineCountEl.textContent = '0';
                        sidebarEmployeeListEl.innerHTML = '<li class="text-muted small" style="padding-left:0;">No employees recently active.</li>';
                    }
                } else if (data !== null) {
                    sidebarOnlineCountEl.textContent = '0';
                    sidebarEmployeeListEl.innerHTML = '<li class="text-warning small" style="padding-left:0;">Data format error.</li>';
                }
            })
            .catch(error => {
                 if (sidebarOnlineCountEl && sidebarOnlineCountEl.textContent !== 'E') sidebarOnlineCountEl.textContent = 'E';
                 if (sidebarEmployeeListEl && sidebarEmployeeListEl.textContent.includes("Loading...")) {
                     sidebarEmployeeListEl.innerHTML = '<li class="text-danger small" style="padding-left:0;">Network error.</li>';
                 }
            });
    }

    // --- Alert Dismissal (Bootstrap handles this with data-bs-dismiss="alert") ---
    // No custom JS needed if Bootstrap JS is loaded and alerts have .alert-dismissible and .btn-close with data-bs-dismiss.

    // --- Initialize Components ---
    setActiveSidebarLink(); // Call on load
    initializeAdminDropdown();
    initializeHelpButton();

    if (sidebarEmployeeListEl && sidebarOnlineCountEl) {
        fetchActiveEmployeesSidebar(); // Initial call
        setInterval(fetchActiveEmployeesSidebar, ACTIVE_EMPLOYEE_POLL_INTERVAL);
    }

    // Listen for Bootstrap collapse events to potentially update icon (optional visual flair)
    const employeesOnlineCollapseElement = document.getElementById('employeesOnlineCollapse');
    if (employeesOnlineCollapseElement && typeof bootstrap !== 'undefined' && bootstrap.Collapse) {
        const collapseToggle = document.querySelector('a[href="#employeesOnlineCollapse"]');
        const collapseIcon = collapseToggle ? collapseToggle.querySelector('.collapse-icon') : null;

        if (collapseIcon) {
            employeesOnlineCollapseElement.addEventListener('show.bs.collapse', function () {
                // collapseIcon.classList.remove('fa-chevron-down');
                // collapseIcon.classList.add('fa-chevron-up'); // Bootstrap handles this via CSS transform on [aria-expanded="true"]
            });
            employeesOnlineCollapseElement.addEventListener('hide.bs.collapse', function () {
                // collapseIcon.classList.remove('fa-chevron-up');
                // collapseIcon.classList.add('fa-chevron-down');
            });
        }
    }

});