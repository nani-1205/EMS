document.addEventListener('DOMContentLoaded', function() {
    'use strict'; // Enforce stricter parsing and error handling

    // --- DOM Element Selectors (cached for performance) ---
    const sidebarNavLinks = document.querySelectorAll('.sidebar-nav a.nav-link');
    const adminMenuButton = document.getElementById('adminMenuButton');
    const adminDropdown = document.getElementById('adminDropdown');
    const helpButton = document.getElementById('helpButton');
    const sidebarOnlineCountEl = document.getElementById('sidebarOnlineCount');
    const sidebarEmployeeListEl = document.getElementById('sidebarEmployeeList');
    const apiEndpointsDiv = document.getElementById('apiEndpoints');

    // --- Configuration ---
    const ACTIVE_EMPLOYEE_POLL_INTERVAL = 30000; // 30 seconds

    // --- Helper Functions ---
    function getApiUrl(dataAttributeName) {
        if (apiEndpointsDiv && apiEndpointsDiv.dataset[dataAttributeName]) {
            return apiEndpointsDiv.dataset[dataAttributeName];
        }
        // console.warn(`API URL data attribute '${dataAttributeName}' not found on #apiEndpoints div.`);
        return null;
    }

    // --- Sidebar Active State ---
    function setActiveSidebarLink() {
        if (!sidebarNavLinks.length) return;

        const currentPath = window.location.pathname;
        let SCRIPT_ROOT = "{{ request.script_root|tojson|safe }}"; // Get SCRIPT_ROOT if app is not at domain root
        if (SCRIPT_ROOT === "null" || SCRIPT_ROOT === "\"\"") SCRIPT_ROOT = "";


        sidebarNavLinks.forEach(link => {
            let linkHref = link.getAttribute('href');
            // If href is absolute, make it relative for comparison
            if (linkHref && linkHref.startsWith(window.location.origin)) {
                linkHref = linkHref.substring(window.location.origin.length);
            }
            // Remove trailing slashes for consistent comparison
            const normalizedCurrentPath = SCRIPT_ROOT + currentPath.replace(/\/$/, "");
            const normalizedLinkHref = linkHref ? SCRIPT_ROOT + linkHref.replace(/\/$/, "") : null;

            if (normalizedLinkHref && normalizedCurrentPath === normalizedLinkHref) {
                link.classList.add('active');
            } else if (normalizedLinkHref && normalizedLinkHref !== SCRIPT_ROOT + "/" && normalizedCurrentPath.startsWith(normalizedLinkHref)) {
                // Handle parent path activation (e.g., /reports should be active if on /reports/activity_log)
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    }

    // --- Admin Dropdown Menu ---
    function initializeAdminDropdown() {
        if (!adminMenuButton || !adminDropdown) return;

        adminMenuButton.addEventListener('click', function(e) {
            e.stopPropagation();
            // Toggle using Bootstrap's API if available, or manual toggle
            if (typeof bootstrap !== 'undefined' && bootstrap.Dropdown) {
                const dropdownInstance = bootstrap.Dropdown.getInstance(adminMenuButton) || new bootstrap.Dropdown(adminMenuButton);
                dropdownInstance.toggle();
            } else { // Manual toggle as fallback
                adminDropdown.style.display = adminDropdown.style.display === 'block' ? 'none' : 'block';
            }
        });

        // Global click listener to close dropdown
        document.addEventListener('click', function(event) {
            if (adminDropdown.style.display === 'block' &&
                !adminMenuButton.contains(event.target) &&
                !adminDropdown.contains(event.target)) {
                if (typeof bootstrap !== 'undefined' && bootstrap.Dropdown) {
                     const dropdownInstance = bootstrap.Dropdown.getInstance(adminMenuButton);
                     if(dropdownInstance) dropdownInstance.hide();
                } else {
                    adminDropdown.style.display = 'none';
                }
            }
        });
        
        // Ensure dropdown items navigate correctly
        adminDropdown.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', function() {
                 if (typeof bootstrap !== 'undefined' && bootstrap.Dropdown) {
                     const dropdownInstance = bootstrap.Dropdown.getInstance(adminMenuButton);
                     if(dropdownInstance) dropdownInstance.hide();
                } else {
                    adminDropdown.style.display = 'none';
                }
                // Navigation will be handled by href
            });
        });
    }

    // --- Help Button ---
    function initializeHelpButton() {
        if (!helpButton) return;
        helpButton.addEventListener('click', function() {
            // Replace with actual help functionality or link
            alert('Help & Support (Feature coming soon!)');
        });
    }

    // --- Employees Online Polling ---
    function fetchActiveEmployeesSidebar() {
        if (!sidebarEmployeeListEl || !sidebarOnlineCountEl) return;

        const activeEmployeesUrl = getApiUrl('activeEmployeesUrl');
        const userEditUrlBase = getApiUrl('userEditUrlBase');

        if (!activeEmployeesUrl || !userEditUrlBase) {
            if (sidebarEmployeeListEl.textContent.includes("Loading...")) { // Show error only once
                sidebarEmployeeListEl.innerHTML = '<li class="text-muted small" style="padding-left:0;">API config missing.</li>';
                sidebarOnlineCountEl.textContent = '-';
            }
            return;
        }

        fetch(activeEmployeesUrl)
            .then(response => {
                if (!response.ok) {
                    // console.error(`Error fetching active employees: ${response.status} ${response.statusText}`);
                    // Avoid logging every poll failure, just update UI subtly if needed
                    if (sidebarOnlineCountEl.textContent !== '?') sidebarOnlineCountEl.textContent = '?';
                    return null;
                }
                return response.json();
            })
            .then(data => {
                if (!sidebarEmployeeListEl || !sidebarOnlineCountEl) return; // Re-check elements

                if (data && Array.isArray(data)) {
                    sidebarEmployeeListEl.innerHTML = ''; // Clear previous list
                    if (data.length > 0) {
                        sidebarOnlineCountEl.textContent = data.length;
                        data.forEach(emp => {
                            const listItem = document.createElement('li');
                            const userEditUrl = userEditUrlBase.replace('EMP_ID_PLACEHOLDER', emp._id || '');
                            
                            const displayName = emp.display_name || emp.employee_id || 'Unnamed';
                            const truncatedName = displayName.length > 18 ? displayName.substring(0, 16) + '...' : displayName;

                            listItem.innerHTML = `
                                <span class="online-dot"></span>
                                <a href="${userEditUrl}" 
                                   title="${displayName} (ID: ${emp.employee_id || 'N/A'})"
                                   style="color: #ecf0f1; text-decoration:none;">
                                   ${truncatedName}
                                </a>`;
                            sidebarEmployeeListEl.appendChild(listItem);
                        });
                    } else {
                        sidebarOnlineCountEl.textContent = '0';
                        sidebarEmployeeListEl.innerHTML = '<li class="text-muted small" style="padding-left:0;">No employees recently active.</li>';
                    }
                } else if (data !== null) { // If data is not null but also not an array
                    // console.warn("Unexpected data format for active employees:", data);
                    sidebarOnlineCountEl.textContent = '0';
                    sidebarEmployeeListEl.innerHTML = '<li class="text-warning small" style="padding-left:0;">Data error.</li>';
                }
                // If data is null, it means an error was handled by the previous .then
            })
            .catch(error => {
                // console.error('Network or other error fetching active employees:', error);
                if (sidebarOnlineCountEl && sidebarOnlineCountEl.textContent !== '?') sidebarOnlineCountEl.textContent = '?';
                // Avoid constant error messages in the UI for polling failures
                if (sidebarEmployeeListEl && sidebarEmployeeListEl.textContent.includes("Loading...")) {
                     sidebarEmployeeListEl.innerHTML = '<li class="text-danger small" style="padding-left:0;">Network error.</li>';
                }
            });
    }

    // --- Alert Dismissal (Using Bootstrap's JS for this is better if available) ---
    function initializeAlertDismissal() {
        const alertElements = document.querySelectorAll('.alert-dismissible');
        alertElements.forEach(function(alert) {
            const closeButton = alert.querySelector('.btn-close');
            if (closeButton) {
                closeButton.addEventListener('click', function() {
                    // If Bootstrap JS is loaded, it handles this. This is a fallback.
                    if (!(typeof bootstrap !== 'undefined' && bootstrap.Alert)) {
                        alert.style.display = 'none';
                    }
                });
            }
        });
    }

    // --- Initialize Components ---
    setActiveSidebarLink();
    initializeAdminDropdown();
    initializeHelpButton();
    initializeAlertDismissal();

    if (sidebarEmployeeListEl && sidebarOnlineCountEl) {
        fetchActiveEmployeesSidebar(); // Initial call
        setInterval(fetchActiveEmployeesSidebar, ACTIVE_EMPLOYEE_POLL_INTERVAL);
    }

});