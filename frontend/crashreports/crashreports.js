/* ============================================================
   CRASH REPORTS — JavaScript
   All posts are stored in MongoDB via Flask API.
   All users see the same shared feed.
   ============================================================ */

// ── API config (matches your existing script.js pattern) ────
const API_BASE = window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost' || !window.location.hostname
    ? 'http://127.0.0.1:5000/api'
    : 'https://ai-sales-analytics.onrender.com/api';

// ── Category metadata ────────────────────────────────────────
const CAT = {
    pricing:     { color: '#e53e3e', bg: 'rgba(229,62,62,0.1)',   label: '💸 Pricing'     },
    prospecting: { color: '#d69e2e', bg: 'rgba(214,158,46,0.1)',  label: '🎯 Prospecting' },
    closing:     { color: '#6366f1', bg: 'rgba(99,102,241,0.1)',  label: '🤝 Closing'     },
    retention:   { color: '#38a169', bg: 'rgba(56,161,105,0.1)',  label: '💔 Retention'   },
    operations:  { color: '#3182ce', bg: 'rgba(49,130,206,0.1)',  label: '⚙️ Operations'  },
};

const AVATAR_COLORS = ['#6366f1','#e53e3e','#38a169','#d69e2e','#3182ce','#805ad5','#dd6b20'];

// ── State ────────────────────────────────────────────────────
let allPosts      = [];
let activeFilter  = 'all';
let selectedCat   = 'pricing';
let anonOn        = false;
let currentUser   = localStorage.getItem('username') || '';
// Track which posts the current user has reacted to (persisted in localStorage)
let myReactions   = JSON.parse(localStorage.getItem('cr_reactions') || '{}');

// ── Guard: redirect if not logged in ────────────────────────
if (!currentUser) {
    window.location.href = '../login.html';
}

// ── Init ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Username in top bar
    document.getElementById('usernameDisplay').textContent = currentUser;

    // Restore theme
    const dark = localStorage.getItem('darkTheme') === 'true';
    if (dark) {
        document.body.classList.add('dark-theme');
        document.getElementById('themeToggle').checked = true;
    }

    // Restore sidebar collapse
    if (localStorage.getItem('sidebarCollapsed') === '1') {
        document.getElementById('appLayout').classList.add('sidebar-collapsed');
    }

    buildSidebarLegend();
    syncCatPills();
    fetchPosts();
    initTabFromHash();
});

// ── Sidebar helpers ──────────────────────────────────────────
function toggleSidebarCollapse() {
    const layout = document.getElementById('appLayout');
    const collapsed = layout.classList.toggle('sidebar-collapsed');
    localStorage.setItem('sidebarCollapsed', collapsed ? '1' : '0');
}

function toggleMobileSidebar() {
    document.getElementById('leftSidebar').classList.toggle('mobile-open');
    document.getElementById('sidebarOverlay').classList.toggle('visible');
}

// ── Theme ────────────────────────────────────────────────────
function toggleTheme() {
    const on = document.getElementById('themeToggle').checked;
    document.body.classList.toggle('dark-theme', on);
    localStorage.setItem('darkTheme', on);
}

// ── Logout ───────────────────────────────────────────────────
function logoutUser() {
    localStorage.removeItem('username');
    window.location.href = '../login.html';
}

// ── Sidebar legend ───────────────────────────────────────────
function buildSidebarLegend() {
    const el = document.getElementById('sidebarLegend');
    el.innerHTML = Object.entries(CAT).map(([k, v]) => `
        <div class="cr-legend-item" onclick="filterFromSidebar('${k}')">
            <div class="cr-legend-dot" style="background:${v.color};"></div>
            <span class="cr-legend-label">${v.label}</span>
        </div>`).join('');
}

function filterFromSidebar(cat) {
    document.querySelectorAll('.cr-filter-pill').forEach(p => {
        p.classList.toggle('active', p.dataset.filter === cat);
    });
    activeFilter = cat;
    renderPosts();
}

// ── Category pill sync ───────────────────────────────────────
function syncCatPills() {
    document.querySelectorAll('#composeCatPills .cr-cat-pill').forEach(p => {
        p.addEventListener('click', (e) => {
            e.stopPropagation();
            selectedCat = p.dataset.cat;
            document.querySelectorAll('#composeCatPills .cr-cat-pill').forEach(x => x.classList.remove('selected'));
            p.classList.add('selected');
        });
    });
}

// ── Anonymous toggle ─────────────────────────────────────────
function toggleAnon() {
    anonOn = !anonOn;
    document.getElementById('anonPill').classList.toggle('on', anonOn);
    document.getElementById('anonBadge').style.display = anonOn ? 'inline-flex' : 'none';
    document.getElementById('anonSubtext').textContent = anonOn
        ? 'Your name will be hidden — shown as "Anonymous"'
        : 'Your name will be visible to others';
}

// ── Filter ───────────────────────────────────────────────────
function setFilter(el, filter) {
    document.querySelectorAll('.cr-filter-pill').forEach(p => p.classList.remove('active'));
    el.classList.add('active');
    activeFilter = filter;
    renderPosts();
}

// ── Tab switching ────────────────────────────────────────────
function switchCrashTab(tab) {
    const postBtn  = document.getElementById('tabPostCrash');
    const viewBtn  = document.getElementById('tabViewCrash');
    const postSec  = document.getElementById('postCrashSection');
    const viewSec  = document.getElementById('viewCrashSection');

    if (tab === 'post') {
        postBtn.classList.add('active');
        viewBtn.classList.remove('active');
        postSec.classList.add('active');
        viewSec.classList.remove('active');
    } else {
        viewBtn.classList.add('active');
        postBtn.classList.remove('active');
        viewSec.classList.add('active');
        postSec.classList.remove('active');
    }
    location.hash = tab;
}

function initTabFromHash() {
    const hash = location.hash.replace('#', '');
    if (hash === 'view') switchCrashTab('view');
}

// ── DB connection status badge ───────────────────────────────
function setDbConnected(connected) {
    const badge = document.getElementById('liveBadge');
    const text  = document.getElementById('liveBadgeText');
    if (connected) {
        badge.classList.add('connected');
        text.textContent = 'Crash Reports — Community';
    } else {
        badge.classList.remove('connected');
        text.textContent = 'Crash Reports — Disconnected';
    }
}

// ── Fetch posts from DB ──────────────────────────────────────
async function fetchPosts() {
    document.getElementById('feedLoading').style.display = 'flex';
    document.getElementById('postsContainer').innerHTML  = '';
    document.getElementById('emptyState').style.display  = 'none';

    try {
        const res  = await fetch(`${API_BASE}/crashreports/posts`);
        const data = await res.json();
        allPosts   = data.posts || [];
        renderPosts();
        updateStats();
        setDbConnected(true);
    } catch (err) {
        console.error('Failed to load posts:', err);
        showToast('Failed to load posts. Check your connection.', true);
        setDbConnected(false);
    } finally {
        document.getElementById('feedLoading').style.display = 'none';
    }
}

// ── Submit new post ──────────────────────────────────────────
async function submitPost() {
    const title    = document.getElementById('postTitle').value.trim();
    const strategy = document.getElementById('postStrategy').value.trim();
    const wrong    = document.getElementById('postWrong').value.trim();
    const lesson   = document.getElementById('postLesson').value.trim();

    if (!title || !strategy || !wrong || !lesson) {
        showToast('Please fill in all required fields.', true);
        return;
    }

    const btn = document.getElementById('submitBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Posting...';

    try {
        const res = await fetch(`${API_BASE}/crashreports/posts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: currentUser,
                anon:     anonOn,
                category: selectedCat,
                title, strategy, wrong, lesson
            })
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'Server error');
        }

        const data = await res.json();
        // Prepend the new post to the top
        allPosts.unshift(data.post);

        // Reset form
        ['postTitle','postStrategy','postWrong','postLesson'].forEach(id => {
            document.getElementById(id).value = '';
        });
        if (anonOn) toggleAnon();

        // Reset filter to all
        activeFilter = 'all';
        document.querySelectorAll('.cr-filter-pill').forEach(p => {
            p.classList.toggle('active', p.dataset.filter === 'all');
        });

        renderPosts();
        updateStats();
        showToast('Your crash report has been posted!');
        switchCrashTab('view');

    } catch (err) {
        console.error('Submit error:', err);
        showToast(err.message || 'Failed to post. Try again.', true);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-paper-plane"></i> Post to Crash Reports';
    }
}

// ── Render posts ─────────────────────────────────────────────
function renderPosts() {
    const container = document.getElementById('postsContainer');
    const empty     = document.getElementById('emptyState');

    const filtered = activeFilter === 'all'
        ? allPosts
        : allPosts.filter(p => p.category === activeFilter);

    if (!filtered.length) {
        container.innerHTML = '';
        empty.style.display = 'block';
        return;
    }

    empty.style.display = 'none';
    container.innerHTML = filtered.map(p => buildPostHTML(p)).join('');
}

// ── Build post HTML ──────────────────────────────────────────
function buildPostHTML(p) {
    const cat      = CAT[p.category] || CAT.pricing;
    const initials = p.anon
        ? '?'
        : (p.author || 'U').split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);
    const avatarBg = p.anon
        ? '#718096'
        : AVATAR_COLORS[Math.abs(hashStr(p.author || '')) % AVATAR_COLORS.length];

    const reactions = myReactions[p.post_id] || {};
    const upClass   = reactions.upvotes   ? 'active-upvote'   : '';
    const metooClass= reactions.metoo     ? 'active-metoo'    : '';
    const bookClass = reactions.bookmarks ? 'active-bookmark'  : '';

    const dateStr = formatDate(p.created_at);
    const isOwner = p.username === currentUser;

    return `
    <div class="cr-post-card" data-id="${esc(p.post_id)}" data-cat="${esc(p.category)}">

        <div class="cr-post-header">
            <div class="cr-post-avatar" style="background:${avatarBg};">${initials}</div>
            <div class="cr-post-meta">
                <div class="cr-post-author">
                    ${p.anon
                        ? `<span>Anonymous</span>
                           <span class="cr-anon-badge"><i class="fas fa-user-secret"></i> Anon</span>`
                        : `<span>${esc(p.author)}</span>`
                    }
                </div>
                <div class="cr-post-date"><i class="fas fa-clock" style="font-size:10px;margin-right:3px;"></i>${dateStr}</div>
            </div>
            <span class="cr-post-cat-badge" style="background:${cat.bg};color:${cat.color};">${cat.label}</span>
            ${isOwner ? `<button class="cr-delete-btn" onclick="deletePost('${esc(p.post_id)}')" title="Delete this report"><i class="fas fa-trash-alt"></i></button>` : ''}
        </div>

        <div class="cr-post-title">${esc(p.title)}</div>

        <div class="cr-post-section">
            <div class="cr-post-section-label"><i class="fas fa-chess"></i> Strategy Tried</div>
            <div class="cr-post-section-text">${esc(p.strategy)}</div>
        </div>

        <div class="cr-post-section">
            <div class="cr-post-section-label" style="color:#e53e3e;"><i class="fas fa-times-circle"></i> What Went Wrong</div>
            <div class="cr-post-section-text">${esc(p.wrong)}</div>
        </div>

        <div class="cr-post-lesson">
            <div class="cr-post-section-label"><i class="fas fa-lightbulb"></i> Key Lesson</div>
            <div class="cr-post-section-text">${esc(p.lesson)}</div>
        </div>

        <div class="cr-post-actions">
            <button class="cr-action-btn ${upClass}"
                    onclick="react('${esc(p.post_id)}','upvotes',this)">
                <i class="fas fa-fire"></i> <span>${p.upvotes || 0}</span>
            </button>
            <button class="cr-action-btn ${metooClass}"
                    onclick="react('${esc(p.post_id)}','metoo',this)">
                <i class="fas fa-hand-paper"></i>
                <span>This happened to me (${p.metoo || 0})</span>
            </button>
            <button class="cr-action-btn ${bookClass}"
                    onclick="react('${esc(p.post_id)}','bookmarks',this)">
                <i class="fas fa-bookmark"></i> <span>${p.bookmarks || 0}</span>
            </button>
            <button class="cr-action-btn copy-btn"
                    onclick="copyLesson('${esc(p.post_id)}')">
                <i class="fas fa-copy"></i> Copy Lesson
            </button>
        </div>

        <!-- Comments Section -->
        <div class="cr-comments-section">
            <button class="cr-comments-toggle" onclick="toggleComments('${esc(p.post_id)}', this)">
                <i class="fas fa-comments"></i>
                <span>Comments (${(p.comments || []).length})</span>
                <i class="fas fa-chevron-down cr-comments-arrow"></i>
            </button>
            <div class="cr-comments-body" id="comments-${esc(p.post_id)}" style="display:none;">
                <div class="cr-comments-list" id="commentsList-${esc(p.post_id)}">
                    ${buildCommentsHTML(p.comments || [])}
                </div>
                <div class="cr-comment-input-row">
                    <input type="text" class="cr-comment-input" id="commentInput-${esc(p.post_id)}" placeholder="Write a comment..." onkeypress="if(event.key==='Enter') addComment('${esc(p.post_id)}')">
                    <button class="cr-comment-send" onclick="addComment('${esc(p.post_id)}')">
                        <i class="fas fa-paper-plane"></i>
                    </button>
                </div>
            </div>
        </div>
    </div>`;
}

// ── React to a post ──────────────────────────────────────────
async function react(postId, type, btn) {
    if (!myReactions[postId]) myReactions[postId] = {};

    const isActive = myReactions[postId][type];
    const action   = isActive ? 'remove' : 'add';

    // Optimistic UI update
    const span = btn.querySelector('span');
    const post = allPosts.find(p => p.post_id === postId);

    if (isActive) {
        myReactions[postId][type] = false;
        if (post) post[type] = Math.max(0, (post[type] || 1) - 1);
        btn.classList.remove('active-upvote', 'active-metoo', 'active-bookmark');
    } else {
        myReactions[postId][type] = true;
        if (post) post[type] = (post[type] || 0) + 1;
        const cls = { upvotes: 'active-upvote', metoo: 'active-metoo', bookmarks: 'active-bookmark' };
        btn.classList.add(cls[type]);
    }

    // Update button text
    if (post) {
        if (type === 'metoo') {
            span.textContent = `This happened to me (${post.metoo})`;
        } else {
            span.textContent = post[type];
        }
    }

    // Persist reactions locally
    localStorage.setItem('cr_reactions', JSON.stringify(myReactions));
    updateStats();

    // Sync with server
    try {
        await fetch(`${API_BASE}/crashreports/posts/${encodeURIComponent(postId)}/react`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reaction: type, action, username: currentUser })
        });
    } catch (err) {
        console.error('Reaction sync failed:', err);
    }
}

// ── Copy lesson to clipboard ─────────────────────────────────
function copyLesson(postId) {
    const post = allPosts.find(p => p.post_id === postId);
    if (!post) return;
    const text = `"${post.lesson}" — Crash Reports, ${post.author}`;
    navigator.clipboard.writeText(text)
        .then(() => showToast('Lesson copied to clipboard!'))
        .catch(() => showToast('Could not copy. Please copy manually.', true));
}

// ── Delete post ──────────────────────────────────────────────
async function deletePost(postId) {
    if (!confirm('Are you sure you want to delete this crash report?')) return;

    try {
        const res = await fetch(`${API_BASE}/crashreports/posts/${encodeURIComponent(postId)}?username=${encodeURIComponent(currentUser)}`, {
            method: 'DELETE'
        });
        const data = await res.json();

        if (!res.ok) {
            showToast(data.error || 'Failed to delete.', true);
            return;
        }

        allPosts = allPosts.filter(p => p.post_id !== postId);
        renderPosts();
        updateStats();
        showToast('Crash report deleted.');
    } catch (err) {
        console.error('Delete failed:', err);
        showToast('Failed to delete. Try again.', true);
    }
}

// ── Comments ─────────────────────────────────────────────────
function buildCommentsHTML(comments) {
    if (!comments.length) return '<p class="cr-no-comments">No comments yet. Be the first!</p>';
    return comments.map(c => {
        const avatarBg = AVATAR_COLORS[Math.abs(hashStr(c.username || '')) % AVATAR_COLORS.length];
        const initials = (c.username || 'U').slice(0, 2).toUpperCase();
        return `
        <div class="cr-comment">
            <div class="cr-comment-avatar" style="background:${avatarBg};">${initials}</div>
            <div class="cr-comment-body">
                <div class="cr-comment-meta">
                    <span class="cr-comment-author">${esc(c.username)}</span>
                    <span class="cr-comment-time">${formatDate(c.created_at)}</span>
                </div>
                <div class="cr-comment-text">${esc(c.text)}</div>
            </div>
        </div>`;
    }).join('');
}

function toggleComments(postId, btn) {
    const body = document.getElementById('comments-' + postId);
    const arrow = btn.querySelector('.cr-comments-arrow');
    const isOpen = body.style.display !== 'none';
    body.style.display = isOpen ? 'none' : 'block';
    arrow.style.transform = isOpen ? '' : 'rotate(180deg)';
}

async function addComment(postId) {
    const input = document.getElementById('commentInput-' + postId);
    const text = input.value.trim();
    if (!text) return;

    input.disabled = true;
    try {
        const res = await fetch(`${API_BASE}/crashreports/posts/${encodeURIComponent(postId)}/comments`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: currentUser, text })
        });

        if (!res.ok) {
            const err = await res.json();
            showToast(err.error || 'Failed to comment.', true);
            return;
        }

        const data = await res.json();
        const post = allPosts.find(p => p.post_id === postId);
        if (post) {
            if (!post.comments) post.comments = [];
            post.comments.push(data.comment);
        }

        // Re-render just the comments list
        const listEl = document.getElementById('commentsList-' + postId);
        if (listEl && post) listEl.innerHTML = buildCommentsHTML(post.comments);

        // Update toggle button count
        const card = document.querySelector(`[data-id="${postId}"]`);
        if (card && post) {
            const toggleSpan = card.querySelector('.cr-comments-toggle span');
            if (toggleSpan) toggleSpan.textContent = `Comments (${post.comments.length})`;
        }

        input.value = '';
        showToast('Comment added!');
    } catch (err) {
        console.error('Comment failed:', err);
        showToast('Failed to add comment.', true);
    } finally {
        input.disabled = false;
        input.focus();
    }
}

// ── Stats ────────────────────────────────────────────────────
function updateStats() {
    document.getElementById('statTotal').textContent   = allPosts.length;
    document.getElementById('statUpvotes').textContent = allPosts.reduce((s, p) => s + (p.upvotes || 0), 0);
    document.getElementById('statMetoo').textContent   = allPosts.reduce((s, p) => s + (p.metoo   || 0), 0);
}

// ── Toast ────────────────────────────────────────────────────
let toastTimer;
function showToast(msg, warn = false) {
    const el   = document.getElementById('cr-toast');
    const icon = document.getElementById('toastIcon');
    document.getElementById('toastMsg').textContent = msg;
    icon.className  = warn ? 'fas fa-exclamation-triangle' : 'fas fa-check-circle';
    el.className    = warn ? 'warn show' : 'show';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('show', 'warn'), 3200);
}

// ── Utilities ────────────────────────────────────────────────
function esc(str) {
    return String(str || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function hashStr(s) {
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
    return h;
}

function formatDate(iso) {
    if (!iso) return 'Just now';
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1)  return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24)  return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    if (days < 7)  return `${days}d ago`;
    return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}
