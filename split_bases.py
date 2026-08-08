import os

with open('templates/base.html', 'r', encoding='utf-8') as f:
    content = f.read()

nav_start = content.find('<nav class="flex-1 overflow-y-auto py-4 px-3 flex flex-col gap-1 custom-scrollbar">')
nav_end = content.find('</nav>', nav_start) + 6

intake_nav = '''<nav class="flex-1 overflow-y-auto py-4 px-3 flex flex-col gap-1 custom-scrollbar">
            <a href="/home" class="px-4 py-3 rounded-xl text-sm font-semibold hover:bg-emerald-800/50 text-emerald-100 transition-colors flex items-center gap-2" style="text-decoration:none;">
                <span>🏠</span> Intake Dashboard
            </a>
            <div class="mt-4 mb-2 px-4 text-xs font-bold text-emerald-400 uppercase tracking-wider">Operations</div>
            <a href="/register-farm" class="px-4 py-3 rounded-xl text-sm font-semibold hover:bg-emerald-800/50 text-emerald-100 transition-colors flex items-center gap-2" style="text-decoration:none;"><span>🏡</span> Farm Registry</a>
            <a href="/loan-services" class="px-4 py-3 rounded-xl text-sm font-semibold hover:bg-emerald-800/50 text-emerald-100 transition-colors flex items-center gap-2" style="text-decoration:none;"><span>💳</span> Loan Services</a>
            <a href="/shares-management" class="px-4 py-3 rounded-xl text-sm font-semibold hover:bg-emerald-800/50 text-emerald-100 transition-colors flex items-center gap-2" style="text-decoration:none;"><span>📈</span> Shares Management</a>
            <a href="/staff/loan-intake" class="px-4 py-3 rounded-xl text-sm font-semibold hover:bg-emerald-800/50 text-emerald-100 transition-colors flex items-center gap-2" style="text-decoration:none;"><span>📞</span> Staff Intake</a>
            <a href="/transport-logistics" class="px-4 py-3 rounded-xl text-sm font-semibold hover:bg-emerald-800/50 text-emerald-100 transition-colors flex items-center gap-2" style="text-decoration:none;"><span>🚜</span> Machinery Logistics</a>
            <a href="/log-yield" class="px-4 py-3 rounded-xl text-sm font-semibold hover:bg-emerald-800/50 text-emerald-100 transition-colors flex items-center gap-2" style="text-decoration:none;"><span>🌾</span> Log Yield Ticket</a>
            <a href="/weighbridge-tickets" class="px-4 py-3 rounded-xl text-sm font-semibold hover:bg-emerald-800/50 text-emerald-100 transition-colors flex items-center gap-2" style="text-decoration:none;"><span>📊</span> Yields Dashboard</a>
</nav>'''

committee_nav = '''<nav class="flex-1 overflow-y-auto py-4 px-3 flex flex-col gap-1 custom-scrollbar">
            <a href="/committee/reporting" class="px-4 py-3 rounded-xl text-sm font-semibold hover:bg-emerald-800/50 text-emerald-100 transition-colors flex items-center gap-2" style="text-decoration:none;">
                <span>📊</span> Executive Dashboard
            </a>
            <div class="mt-4 mb-2 px-4 text-xs font-bold text-emerald-400 uppercase tracking-wider">Committee Portal</div>
            <a href="/staff/credit-committee" class="px-4 py-3 rounded-xl text-sm font-semibold hover:bg-emerald-800/50 text-emerald-100 transition-colors flex items-center gap-2" style="text-decoration:none;"><span>🏛️</span> Credit Review</a>
            <a href="/committee/shares" class="px-4 py-3 rounded-xl text-sm font-semibold hover:bg-emerald-800/50 text-emerald-100 transition-colors flex items-center gap-2" style="text-decoration:none;"><span>⚖️</span> Share Approvals</a>
            <a href="/committee/pin-requests" class="px-4 py-3 rounded-xl text-sm font-semibold hover:bg-emerald-800/50 text-emerald-100 transition-colors flex items-center gap-2" style="text-decoration:none;"><span>🔐</span> PIN Requests</a>
</nav>'''

assessor_nav = '''<nav class="flex-1 overflow-y-auto py-4 px-3 flex flex-col gap-1 custom-scrollbar">
            <a href="/staff/field-assessor" class="px-4 py-3 rounded-xl text-sm font-semibold hover:bg-emerald-800/50 text-emerald-100 transition-colors flex items-center gap-2" style="text-decoration:none;">
                <span>📋</span> Assessor Dashboard
            </a>
            <div class="mt-4 mb-2 px-4 text-xs font-bold text-emerald-400 uppercase tracking-wider">Assessor Actions</div>
            <a href="/staff/field-assessor" class="px-4 py-3 rounded-xl text-sm font-semibold hover:bg-emerald-800/50 text-emerald-100 transition-colors flex items-center gap-2" style="text-decoration:none;"><span>📋</span> Field Workspace</a>
</nav>'''

admin_nav = content[nav_start:nav_end].replace("{% if session.get('user_role') in ['Intake Agent', 'System Admin'] %}", "").replace("{% if session.get('user_role') in ['Intake Agent', 'Committee Member', 'System Admin'] %}", "").replace("{% if session.get('user_role') == 'Field Assessor' %}", "").replace("{% if session.get('user_role') in ['Committee Member', 'System Admin'] %}", "").replace("{% if session.get('user_role') == 'System Admin' %}", "").replace("{% endif %}", "")

def write_base(name, nav):
    new_content = content[:nav_start] + nav + content[nav_end:]
    with open('templates/' + name, 'w', encoding='utf-8') as f:
        f.write(new_content)

write_base('base_intake.html', intake_nav)
write_base('base_committee.html', committee_nav)
write_base('base_assessor.html', assessor_nav)
write_base('base_admin.html', admin_nav)
