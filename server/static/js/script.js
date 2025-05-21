// server/static/js/script_task.js

document.addEventListener('DOMContentLoaded', function() {
 const sidebarNavLinks = document.querySelectorAll('.sidebar-nav a.nav-link');
 const adminMenuButton = document.getElementById('adminMenuButton');
 const adminDropdown = document.getElementById('adminDropdown');
 const logoutButton = document.getElementById('logoutButton');
 const helpButton = document.getElementById('helpButton');

 const sidebarOnlineCount = document.getElementById('sidebarOnlineCount');
 const sidebarEmployeeList = document.getElementById('sidebarEmployeeList');
 const apiEndpointsDiv = document.getElementById('apiEndpoints'); // For API URLs

 // --- Active State for Sidebar Links based on current Flask route ---
 const currentPath = window.location.pathname;
 sidebarNavLinks.forEach(link => {
     const linkHref = link.getAttribute('href');
     // Check if current path starts with the link's href (for parent sections)
     // or is an exact match.
     if (linkHref && (currentPath === linkHref || (currentPath.startsWith(linkHref) && linkHref !== '/'))) {
         link.classList.add('active');

         // Special handling to keep main "Reports" or "Settings" active if on a sub-page
         if (currentPath.startsWith("/reports/") && linkHref === "{{ url_for('reports.index') }}") { // Using Jinja as placeholder
              link.classList.add('active');
         } else if (currentPath.startsWith("/settings/") && linkHref === "{{ url_for('settings.index') }}") {
              link.classList.add('active');
         }

     } else {
         link.classList.remove('active');
     }
     // Handle data-target for client-side view switching IF you re-implement it
     // For now, we assume Flask serves each page.
     // If link has data-route (from older task.html logic), prefer actual href for active state.
 });
 
 // If on a specific report page, ensure the main "Reports" sidebar link is also active
 if (currentPath.startsWith("/reports/") && currentPath !== "{{ url_for('reports.index') }}") {
     const mainReportsLink = document.querySelector('.sidebar-nav a[href="{{ url_for(\'reports.index\') }}"]');
     if(mainReportsLink) mainReportsLink.classList.add('active');
 }
 // If on a specific settings sub-page (if any), ensure main "Settings" is active
 if (currentPath.startsWith("/settings/") && currentPath !== "{{ url_for('settings.index') }}") {
     const mainSettingsLink = document.querySelector('.sidebar-nav a[href="{{ url_for(\'settings.index\') }}"]');
     if(mainSettingsLink) mainSettingsLink.classList.add('active');
 }


 // --- Admin Dropdown ---
 if (adminMenuButton && adminDropdown) {
     adminMenuButton.addEventListener('click', function(e) {
         e.stopPropagation(); // Prevent click from immediately closing due to document listener
         adminDropdown.style.display = adminDropdown.style.display === 'block' ? 'none' : 'block';
     });

     // Close dropdown if clicked outside
     document.addEventListener('click', function(event) {
         if (adminDropdown.style.display === 'block' && 
             !adminMenuButton.contains(event.target) && 
             !adminDropdown.contains(event.target)) {
             adminDropdown.style.display = 'none';
         }
     });
     
     // Handle clicks on dropdown items that are for client-side page switching
     // (This is from task.html's original SPA logic)
     adminDropdown.querySelectorAll('a.nav-link[data-target]').forEach(link => {
         link.addEventListener('click', function(e) {
             // For a Flask app, these should ideally be server-side routes
             // If you keep client-side switching, this code would stay.
             // For now, server-side navigation via href is preferred.
             if(this.dataset.route) {
                 // Let the href handle navigation
             } else {
                 e.preventDefault(); // Prevent if it's purely client-side target
                 // showPage(this.dataset.target); // You'd need to re-implement showPage
             }
             adminDropdown.style.display = 'none';
         });
     });
 }

 // --- Logout (href in layout.html already points to Flask's /auth/logout) ---
 if (logoutButton) {
     // No specific JS needed if it's just a link.
 }
         
 // --- Help Button ---
 if (helpButton) {
     helpButton.addEventListener('click', function() {
         alert('Help feature is currently under development.'); // Placeholder
     });
 }

 // --- EMPLOYEES ONLINE POLLING ---
 function fetchActiveEmployeesSidebar() {
     if (!sidebarEmployeeList || !sidebarOnlineCount || !apiEndpointsDiv) return;
     
     const activeEmployeesUrl = apiEndpointsDiv.dataset.activeEmployeesUrl;
     const userEditUrlBase = apiEndpointsDiv.dataset.userEditUrlBase;

     if (!activeEmployeesUrl || !userEditUrlBase) {
         // console.warn("API URLs for sidebar not found in data attributes.");
         // To avoid console spam on pages where it might not be critical
         if (sidebarEmployeeList.textContent.includes("Loading...")) {
              sidebarEmployeeList.innerHTML = '<li class="text-muted small" style="padding-left:0;">Could not load.</li>';
              sidebarOnlineCount.textContent = '-';
         }
         return;
     }

     fetch(activeEmployeesUrl)
         .then(response => {
             if (!response.ok) {
                 console.error(`Error fetching active employees: ${response.status} ${response.statusText}`);
                 return null; 
             }
             return response.json();
         })
         .then(data => {
             if (!sidebarEmployeeList || !sidebarOnlineCount) return;

             if (data && Array.isArray(data)) {
                 sidebarEmployeeList.innerHTML = ''; 
                 if (data.length > 0) {
                     sidebarOnlineCount.textContent = data.length;
                     data.forEach(emp => {
                         const listItem = document.createElement('li');
                         let userEditUrl = userEditUrlBase.replace('EMP_ID_PLACEHOLDER', emp._id);
                         
                         listItem.innerHTML = `<span class="online-dot"></span> <a href="${userEditUrl}" style="color: #ecf0f1; text-decoration:none;" title="${emp.display_name || 'N/A'} (ID: ${emp.employee_id || 'N/A'})">${(emp.display_name || 'Unnamed').substring(0,18)}${(emp.display_name && emp.display_name.length > 18) ? '...' : ''}</a>`;
                         sidebarEmployeeList.appendChild(listItem);
                     });
                 } else {
                     sidebarOnlineCount.textContent = '0';
                     sidebarEmployeeList.innerHTML = '<li class="text-muted small" style="padding-left:0;">No employees recently active.</li>';
                 }
             } else if (data === null) {
                 // Error handled by previous .then
             } else {
                 // console.warn("Unexpected data format for active employees:", data);
                 sidebarOnlineCount.textContent = '0';
                 sidebarEmployeeList.innerHTML = '<li class="text-warning small" style="padding-left:0;">Data error.</li>';
             }
         })
         .catch(error => {
             // console.error('Network or other error fetching active employees:', error);
              if (sidebarOnlineCount) sidebarOnlineCount.textContent = '?';
              if (sidebarEmployeeList && sidebarEmployeeList.textContent.includes("Loading...")) {
                  sidebarEmployeeList.innerHTML = '<li class="text-danger small" style="padding-left:0;">Network error.</li>';
              }
         });
 }
 
 if (sidebarEmployeeList && sidebarOnlineCount && apiEndpointsDiv) {
     fetchActiveEmployeesSidebar();
     setInterval(fetchActiveEmployeesSidebar, 30000); // Poll every 30 seconds
 }

 // Dismiss alerts
 const alerts = document.querySelectorAll('.alert-dismissible');
 alerts.forEach(function(alert) {
     const closeButton = alert.querySelector('.btn-close');
     if (closeButton) {
         closeButton.addEventListener('click', function() {
             alert.style.display = 'none';
         });
     }
 });

});