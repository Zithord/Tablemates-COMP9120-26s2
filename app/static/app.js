const state = {
  user: null, page: 'explore', catalog: null, favorites: new Set(), sequence: 0,
  filters: {q: '', suburb: '', cuisine: '', price_level: '', min_rating: '', sort: 'rating', friends_only: '0'},
  friendQuery: '', offsets: {explore: 0, records: 0}, detail: null
};
const PAGE_SIZE = 20;
const $ = selector => document.querySelector(selector);
const html = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const dateText = value => value ? new Date(value).toLocaleDateString('en-AU') : '—';
const ratingText = value => value == null ? 'New' : Number(value).toFixed(1);
const params = values => new URLSearchParams(Object.entries(values).filter(([, value]) => value !== '' && value != null));
const localDate = () => {const now = new Date(); return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);};
const avatar = name => `<span class="avatar">${html(String(name).split(' ').slice(0, 2).map(part => part[0]).join(''))}</span>`;
const button = (label, action, id, extra = '', style = 'button-outline') => `<button type="button" class="button button-small ${style}" data-action="${action}" data-id="${id}" ${extra}>${label}</button>`;
const heading = (title, description) => `<div class="page-heading"><span class="eyebrow">TABLEMATES</span><h1>${title}</h1><p>${description}</p></div>`;
const section = title => `<div class="section-head"><h2>${title}</h2></div>`;
const empty = (title, text) => `<div class="empty-state"><h3>${title}</h3><p>${text}</p></div>`;

async function api(path, options = {}) {
  const request = {method: options.method || 'GET', credentials: 'same-origin', headers: {Accept: 'application/json'}};
  if (options.data !== undefined) {
    request.headers['Content-Type'] = 'application/json';
    request.body = JSON.stringify(options.data);
  }
  const result = await fetch(path, request);
  if (result.status === 204) return {};
  let data;
  try {data = await result.json();} catch {throw new Error(`Server returned ${result.status}.`);}
  if (!result.ok) {
    const error = new Error(data.error || 'Request failed.');
    error.status = result.status;
    throw error;
  }
  return data;
}

function toast(message, error = false) {
  const item = document.createElement('div');
  item.className = `toast${error ? ' error' : ''}`;
  item.textContent = message;
  $('#toast-root').append(item);
  setTimeout(() => item.remove(), 4500);
}
function modal(title, content, wide = false) {
  $('#modal-root').innerHTML = `<div class="modal-backdrop" data-action="close-backdrop"><div class="modal ${wide ? 'wide' : ''}" role="dialog" aria-modal="true" aria-label="${html(title)}"><div class="modal-header"><h2>${html(title)}</h2><button type="button" class="icon-button" data-action="close-modal" aria-label="Close">×</button></div>${content}</div></div>`;
  document.body.style.overflow = 'hidden';
  $('.modal-header button')?.focus();
}
function closeModal() {
  $('#modal-root').innerHTML = '';
  document.body.style.overflow = '';
}
function showAuth() {
  closeModal();
  $('#auth-screen').hidden = false;
  $('#app-shell').hidden = true;
}
function authMode(mode) {
  $('#login-form').hidden = mode !== 'login';
  $('#register-form').hidden = mode !== 'register';
  $('#auth-title').textContent = mode === 'register' ? 'Join the table.' : 'Pull up a chair.';
  document.querySelectorAll('[data-action="auth-mode"]').forEach(item => item.classList.toggle('active', item.dataset.mode === mode));
}
async function enterApp(user) {
  state.user = user;
  state.catalog = await api('/api/catalog');
  const saved = await api('/api/favorites');
  state.favorites = new Set(saved.items.map(item => Number(item.restaurant_id)));
  state.offsets = {explore: 0, records: 0};
  state.filters.friends_only = '0';
  $('#auth-screen').hidden = true;
  $('#app-shell').hidden = false;
  $('#sidebar-name').textContent = user.user_name;
  $('#sidebar-email').textContent = user.user_email;
  await navigate('explore');
}
async function navigate(page) {
  const names = {explore: 'Explore restaurants', friends: 'Friends', saved: 'Saved places', records: 'My visits & reviews'};
  if (!names[page]) return;
  state.page = page;
  const sequence = ++state.sequence;
  $('#topbar-title').textContent = names[page];
  $('#sidebar').classList.remove('open');
  document.querySelectorAll('[data-page]').forEach(item => item.classList.toggle('active', item.dataset.page === page));
  $('#main-content').innerHTML = '<div class="loading-state">Loading…</div>';
  try {
    const content = await ({explore: explorePage, friends: friendsPage, saved: savedPage, records: recordsPage}[page])();
    if (sequence === state.sequence) $('#main-content').innerHTML = content;
  } catch (error) {
    if (error.status === 401) {state.user = null; showAuth();}
    else if (sequence === state.sequence) $('#main-content').innerHTML = `<div class="error-state"><h3>Unable to load</h3><p>${html(error.message)}</p>${button('Try again', 'retry', '')}</div>`;
  }
}
function pagination(page, offset, hasNext) {
  return `<div class="pagination">${button('Previous', 'page', page, `data-offset="${Math.max(0, offset - PAGE_SIZE)}" ${offset === 0 ? 'disabled' : ''}`)}<small>Page ${Math.floor(offset / PAGE_SIZE) + 1}</small>${button('Next', 'page', page, `data-offset="${offset + PAGE_SIZE}" ${hasNext ? '' : 'disabled'}`)}</div>`;
}
// Cuisine photos from Unsplash (free to use under the Unsplash License). Presentation only: not stored in the database.
const CUISINE_PHOTOS = {
  'Cafe': ['1564327367919-cb377ea6a88f', '1760175445000-0e01e193d1cd', '1551266681-ba5f0b95e2e5'],
  'Chinese': ['1563245372-f21724e3856d', '1496116218417-1a781b1c416c', '1534422298391-e4f8c172dddb'],
  'Indian': ['1565557623262-b51c2513a641', '1631452180539-96aca7d48617', '1767114915989-c6ab3c8fc42e'],
  'Italian': ['1498579150354-977475b7ea0b', '1784649667262-fd1bb54c384f', '1447279506476-3faec8071eee'],
  'Japanese': ['1579871494447-9811cf80d66c', '1553621042-f6e147245754', '1569718212165-3a8278d5f624'],
  'Korean': ['1498654896293-37aacf113fd9', '1774428755031-0991c8901f08', '1693429308125-3be7b105ad56'],
  'Mexican': ['1599974579688-8dbdd335c77f', '1613514785940-daed07799d9b', '1771308354374-3d9ad8970483'],
  'Middle Eastern': ['1542528180-0c79567c66de', '1787069789754-636ce94929e5'],
  'Modern Australian': ['1616671276441-2f2c277b8bf9', '1616669944447-d65d41a222bd', '1703849133132-98c23595b981'],
  'Seafood': ['1651323018466-b36b7df1d2b1', '1765100479761-2359e22fbe16', '1557267725-c530b236f446'],
  'Thai': ['1655091273851-7bdc2e578a88', '1772729219154-2f5d5ddd732b', '1559314809-0d155014e29e'],
  'Vietnamese': ['1631709497146-a239ef373cf1', '1582878826629-29b7ad1cdc43', '1766050586763-723571af4dde'],
};
function restaurantPhoto(restaurant, width = 640, height = 300) {
  const ids = CUISINE_PHOTOS[(restaurant.cuisines || [])[0]];
  if (!ids) return '';
  const photoId = ids[Number(restaurant.restaurant_id) % ids.length];
  return `https://images.unsplash.com/photo-${photoId}?w=${width}&h=${height}&fit=crop&auto=format&q=75`;
}
function restaurantCard(restaurant) {
  const id = Number(restaurant.restaurant_id), saved = state.favorites.has(id);
  const names = (restaurant.friend_names || []).slice(0, 3).map(html).join(', ');
  return `<article class="restaurant-card card"><div class="restaurant-art"><span aria-hidden="true">🍽️</span>${restaurantPhoto(restaurant) ? `<img class="restaurant-photo" src="${restaurantPhoto(restaurant)}" alt="" loading="lazy" onerror="this.remove()">` : ''}<button class="icon-button save-button ${saved ? 'is-saved' : ''}" type="button" data-action="favorite" data-id="${id}" aria-label="${saved ? 'Unsave' : 'Save'} restaurant">${saved ? '♥' : '♡'}</button></div><div class="restaurant-card-body"><div class="restaurant-meta">${html(restaurant.cuisines?.join(' · ') || restaurant.suburb)}</div><h3><button type="button" data-action="restaurant" data-id="${id}">${html(restaurant.restaurant_name)}</button></h3><div class="restaurant-address">${html(restaurant.street_address)} · ${html(restaurant.suburb)}</div><div class="restaurant-bottom"><span class="rating-star">★</span><strong>${ratingText(restaurant.avg_rating)}</strong><span>(${html(restaurant.review_count)} reviews)</span><span class="price">${'$'.repeat(restaurant.price_level)}</span></div>${restaurant.friend_visit_count > 0 ? `<div class="friend-visit-note"><strong>${restaurant.friend_visit_count} friend(s) visited in the last 90 days</strong><small>${names}${restaurant.friend_visit_count > 3 ? ' and more' : ''}</small></div>` : ''}</div></article>`;
}
async function explorePage() {
  const filters = state.filters, offset = state.offsets.explore;
  const {items} = await api('/api/restaurants?' + params({...filters, limit: PAGE_SIZE + 1, offset}));
  const options = (list, key, selected) => list.map(item => `<option value="${html(item[key])}" ${item[key] === selected ? 'selected' : ''}>${html(item[key])}</option>`).join('');
  return heading('Find your next good table.', 'Explore restaurants and discover where your friends have been.') +
    `<form id="filter-form" class="filter-bar card">
      <div class="form-field search-field"><label for="filter-q">Restaurant name</label><input id="filter-q" name="q" value="${html(filters.q)}" maxlength="100" placeholder="Search restaurants"></div>
      <div class="form-field"><label for="filter-suburb">Suburb</label><select id="filter-suburb" name="suburb"><option value="">All suburbs</option>${options(state.catalog.suburbs, 'name', filters.suburb)}</select></div>
      <div class="form-field"><label for="filter-cuisine">Cuisine</label><select id="filter-cuisine" name="cuisine"><option value="">All cuisines</option>${options(state.catalog.cuisines, 'cuisine_name', filters.cuisine)}</select></div>
      <div class="form-field"><label for="filter-price">Price level</label><select id="filter-price" name="price_level"><option value="">Any price</option>${[1,2,3,4].map(n => `<option value="${n}" ${String(n) === filters.price_level ? 'selected' : ''}>${'$'.repeat(n)}</option>`).join('')}</select></div>
      <div class="form-field"><label for="filter-rating">Minimum rating</label><select id="filter-rating" name="min_rating"><option value="">Any rating</option>${[3,4,4.5].map(n => `<option value="${n}" ${String(n) === filters.min_rating ? 'selected' : ''}>${n}+</option>`).join('')}</select></div>
      <div class="form-field"><label for="filter-sort">Sort by</label><select id="filter-sort" name="sort">${[['rating','Highest rating'],['reviews','Most reviews'],['name','Name'],['price','Price'],['friends','Recent friend visits']].map(([value,label]) => `<option value="${value}" ${value === filters.sort ? 'selected' : ''}>${label}</option>`).join('')}</select></div>
      <div class="filter-actions"><button class="button button-primary" type="submit">Apply filters</button>${button('Reset', 'clear-filters', '')}</div>
    </form>
    <div class="friends-filter-strip"><span>${filters.friends_only === '1' ? 'Showing restaurants recently visited by your friends' : 'Discover restaurants through your friends'}</span>${button(filters.friends_only === '1' ? 'Show all restaurants' : 'Friends visited only', 'toggle-friends-filter', '')}</div>
    ${items.length ? `<div class="restaurant-grid">${items.slice(0, PAGE_SIZE).map(restaurantCard).join('')}</div>` : empty('No matching restaurants', 'Try changing your filters or connect with more friends.')}
    ${pagination('explore', offset, items.length > PAGE_SIZE)}`;
}
function personRow(name, description, actions) {
  return `<div class="person-row">${avatar(name)}<div class="person-info"><strong>${html(name)}</strong><p>${html(description)}</p></div><div class="row-actions">${actions}</div></div>`;
}
async function friendsPage() {
  const [{items}, people] = await Promise.all([api('/api/friends'), api('/api/users?' + params({q: state.friendQuery}))]);
  const incoming = items.filter(item => item.status === 'pending' && item.direction === 'received');
  const accepted = items.filter(item => item.status === 'accepted');
  const other = items.filter(item => item.status !== 'accepted' && !incoming.includes(item));
  return heading('Your friends.', 'Connect with people whose restaurant opinions you trust.') +
    `<div class="two-col"><section>${section('Incoming requests')}${incoming.length ? `<div class="stack">${incoming.map(item => personRow(item.other_user_name, 'Wants to connect', button('Accept','friend-decision',item.friendship_id,'data-decision="accept"','button-primary') + button('Decline','friend-decision',item.friendship_id,'data-decision="reject"'))).join('')}</div>` : empty('No pending requests','New requests will appear here.')}
    ${section(`Friends (${accepted.length})`)}<div class="stack">${accepted.map(item => personRow(item.other_user_name,'Connected','')).join('') || empty('No friends yet','Search for someone below.')}</div>
    ${section('Other requests')}<div class="stack">${other.map(item => personRow(item.other_user_name, item.direction + ' · ' + item.status,'')).join('') || '<p class="muted">No other requests.</p>'}</div></section>
    <section>${section('Find people')}<form id="friend-search-form" class="search-form"><input aria-label="Search people" name="q" value="${html(state.friendQuery)}" placeholder="Search by name" maxlength="100"><button type="submit" class="button button-dark">Search</button></form><div class="stack">${people.items.map(item => personRow(item.user_name,item.friendship_status || 'Not connected',item.friendship_status ? `<span class="status-pill ${html(item.friendship_status)}">${html(item.friendship_status)}</span>` : button('Add friend','send-request',item.user_id))).join('') || empty('No matches','Try another name.')}</div></section></div>`;
}
async function savedPage() {
  const {items} = await api('/api/favorites');
  return heading('Saved places.', 'Your shortlist for another day.') +
    (items.length ? `<div class="restaurant-grid">${items.map(restaurantCard).join('')}</div>` : empty('Nothing saved yet','Save a restaurant using its heart button.'));
}
async function recordsPage() {
  const offset = state.offsets.records;
  const {items} = await api('/api/me/visits?' + params({limit: PAGE_SIZE + 1, offset}));
  return heading('My visits & reviews.', 'Record a visit, add a review, or update your own experience.') +
    `<div class="stack">${items.slice(0,PAGE_SIZE).map(item => `<article class="visit-row"><h3><button class="link-like" type="button" data-action="restaurant" data-id="${item.restaurant_id}">${html(item.restaurant_name)}</button></h3><small>Visited ${html(item.visit_date)} · Party of ${item.party_size}${item.review_id ? ` · ★ ${item.rating}/5` : ' · Not reviewed yet'}</small>${item.review_id ? `<p>${html(item.review_text)}</p><div class="row-actions">${button('Edit review','edit-review',item.review_id)}${button('Delete review','delete-review',item.review_id,'','button-danger')}${button('Comments','comments',item.review_id)}</div>` : `<div class="row-actions">${button('Add review','review-visit',item.visit_id)}</div>`}</article>`).join('') || empty('No visits yet','Record your first visit using the button above.')}</div>${pagination('records',offset,items.length > PAGE_SIZE)}`;
}
function reviewRow(review, conversation = false) {
  const owner = state.user && Number(review.user_id) === Number(state.user.user_id);
  return `<article class="review-row"><div class="review-top">${avatar(review.user_name)}<div><strong>${html(review.user_name)}</strong><small>Visited ${html(review.visit_date)}</small></div><span class="rating">★ ${review.rating}/5</span></div><p>${html(review.review_text)}</p><div class="row-actions">${conversation ? '' : button('Comments','comments',review.review_id)}${owner ? button('Edit','edit-review',review.review_id) + button('Delete','delete-review',review.review_id,'','button-danger') : ''}</div></article>`;
}
async function restaurantDetail(id, scope = 'all', offset = 0) {
  state.detail = {id, scope, offset};
  const [detail, reviews, friends] = await Promise.all([
    api(`/api/restaurants/${id}`),
    api(`/api/restaurants/${id}/reviews?` + params({friends_only: scope === 'friends' ? '1' : '0', limit: PAGE_SIZE + 1, offset})),
    api(`/api/restaurants/${id}/friend-visits`)
  ]);
  const r = detail.restaurant;
  modal(r.restaurant_name, `${restaurantPhoto(r, 960, 360) ? `<img class="detail-photo" src="${restaurantPhoto(r, 960, 360)}" alt="" onerror="this.remove()">` : ''}<p class="muted">${html(r.street_address)} · ${html(r.suburb)} · ${html(r.cuisines.join(' · '))}</p><p>★ <strong>${ratingText(r.avg_rating)}</strong> · ${r.review_count} reviews · ${'$'.repeat(r.price_level)}</p><div class="detail-controls">${button('Record a visit','write-review',id,'','button-primary')}${button(state.favorites.has(Number(id)) ? '♥ Saved' : '♡ Save place','favorite',id)}</div>
    <div class="friend-detail-panel"><strong>${friends.friend_count} friend(s) visited in the last 90 days</strong><div class="friend-visit-list">${friends.items.map(item => `<div class="friend-visit-person">${html(item.user_name)}<small>${html(item.visit_date)}</small></div>`).join('') || 'No recent friend visits.'}</div></div>
    ${section('Restaurant reviews')}<div class="review-tabs">${['all','friends'].map(value => `<button type="button" class="${scope === value ? 'active' : ''}" data-action="review-scope" data-id="${id}" data-scope="${value}">${value === 'all' ? 'All reviews' : 'Friends only'}</button>`).join('')}</div>
    <div class="review-list">${reviews.items.slice(0,PAGE_SIZE).map(item => reviewRow(item)).join('') || empty('No reviews here yet','Try all reviews or share your own experience.')}</div>
    <div class="pagination">${button('Previous','review-page',id,`data-offset="${Math.max(0,offset-PAGE_SIZE)}" ${offset === 0 ? 'disabled' : ''}`)}<small>Page ${Math.floor(offset/PAGE_SIZE)+1}</small>${button('Next','review-page',id,`data-offset="${offset+PAGE_SIZE}" ${reviews.items.length > PAGE_SIZE ? '' : 'disabled'}`)}</div>`, true);
}
async function commentsModal(id) {
  const [{review},{items}] = await Promise.all([api(`/api/reviews/${id}`),api(`/api/reviews/${id}/comments`)]);
  const byId = new Map(items.map(item => [Number(item.comment_id),item]));
  modal('Review conversation', `${reviewRow(review,true)}${section(`Comments (${items.length})`)}<div class="stack">${items.map(item => `<div class="comment-row ${item.parent_comment_id ? 'reply-row' : ''}"><strong>${html(item.author_name)}</strong><small>${dateText(item.created_at)}</small>${item.parent_comment_id ? `<div class="reply-note">Reply to ${html(byId.get(Number(item.parent_comment_id))?.author_name || 'another comment')}</div>` : ''}<p>${html(item.comment_text)}</p><div class="row-actions">${button('Reply','reply-comment',item.comment_id,`data-author="${html(item.author_name)}"`)}</div></div>`).join('') || empty('Start a conversation','No comments yet.')}</div>
    <form id="comment-form" data-id="${id}" class="form-stack"><p id="reply-context" class="muted" hidden></p><input type="hidden" name="parent_comment_id" value=""><label for="comment-text">Your comment</label><textarea id="comment-text" name="comment_text" required maxlength="1000"></textarea><div class="form-actions">${button('Clear reply','clear-reply','')}<button class="button button-primary" type="submit">Post comment</button></div></form>`, true);
}
async function reviewModal({restaurantId = '', visitId = '', reviewId = ''} = {}) {
  const editing = reviewId ? (await api(`/api/reviews/${reviewId}`)).review : null;
  const places = !restaurantId && !visitId && !editing ? (await api('/api/restaurants?limit=50&sort=name')).items : [];
  const required = visitId || editing;
  modal(editing ? 'Edit your review' : visitId ? 'Review your visit' : 'Record a restaurant visit',
    `<form id="review-form" data-restaurant="${restaurantId}" data-visit="${visitId}" data-review="${reviewId}" class="form-grid">
    ${places.length ? `<div class="form-field full"><label for="review-restaurant">Restaurant</label><select id="review-restaurant" name="restaurant_id" required><option value="">Choose a restaurant</option>${places.map(item => `<option value="${item.restaurant_id}">${html(item.restaurant_name)}</option>`).join('')}</select></div>` : ''}
    ${!required ? `<div class="form-field"><label for="review-date">Visit date</label><input id="review-date" name="visit_date" type="date" max="${localDate()}" value="${localDate()}" required></div><div class="form-field"><label for="review-party">Party size</label><input id="review-party" name="party_size" type="number" min="1" max="30" value="2" required></div>` : ''}
    <div class="form-field full"><label for="review-rating">Overall restaurant rating</label><select id="review-rating" name="rating" ${required ? 'required' : ''}>${!required ? '<option value="">Record visit without a review</option>' : ''}${[5,4,3,2,1].map(n => `<option value="${n}" ${n === (editing?.rating || 5) ? 'selected' : ''}>${n}/5</option>`).join('')}</select></div>
    <div class="form-field full"><label for="review-text">Your review</label><textarea id="review-text" name="review_text" maxlength="5000" ${required ? 'required' : ''} placeholder="Review the restaurant overall; leave blank if recording a visit without a review.">${html(editing?.review_text || '')}</textarea></div>
    <div class="form-actions full">${button('Cancel','close-modal','')}<button class="button button-primary" type="submit">${editing ? 'Save changes' : 'Save visit & review'}</button></div></form>`);
}
async function performAction(item) {
  const action = item.dataset.action, id = item.dataset.id;
  if (action === 'auth-mode') {authMode(item.dataset.mode); return;}
  if (action === 'close-modal') {closeModal(); return;}
  if (action === 'toggle-menu') {$('#sidebar').classList.toggle('open'); return;}
  if (action === 'retry') {await navigate(state.page); return;}
  if (action === 'page') {state.offsets[id] = Number(item.dataset.offset); await navigate(id); return;}
  if (action === 'clear-filters') {state.filters = {q:'',suburb:'',cuisine:'',price_level:'',min_rating:'',sort:'rating',friends_only:'0'}; state.offsets.explore = 0; await navigate('explore'); return;}
  if (action === 'toggle-friends-filter') {state.filters.friends_only = state.filters.friends_only === '1' ? '0' : '1'; state.offsets.explore = 0; await navigate('explore'); return;}
  if (action === 'demo-login') {const {user} = await api('/api/login',{method:'POST',data:{email:'alice.morgan@example.test',password:'DemoPass2026!'}}); await enterApp(user); return;}
  if (action === 'logout') {await api('/api/logout',{method:'POST'}); state.user = null; showAuth(); return;}
  if (action === 'restaurant') {await restaurantDetail(id); return;}
  if (action === 'review-scope') {await restaurantDetail(id,item.dataset.scope); return;}
  if (action === 'review-page') {await restaurantDetail(id,state.detail.scope,Number(item.dataset.offset)); return;}
  if (action === 'favorite') {
    const saved = state.favorites.has(Number(id));
    await api(saved ? `/api/favorites/${id}` : '/api/favorites',{method:saved ? 'DELETE' : 'POST',data:saved ? undefined : {restaurant_id:Number(id)}});
    saved ? state.favorites.delete(Number(id)) : state.favorites.add(Number(id));
    toast(saved ? 'Removed from saved places.' : 'Restaurant saved.');
    if ($('#modal-root').innerHTML) await restaurantDetail(id,state.detail?.scope || 'all',state.detail?.offset || 0);
    else await navigate(state.page);
    return;
  }
  if (action === 'friend-decision') {await api(`/api/friend-requests/${id}/${item.dataset.decision}`,{method:'POST'}); toast('Friend request updated.'); await navigate('friends'); return;}
  if (action === 'send-request') {await api('/api/friend-requests',{method:'POST',data:{addressee_id:Number(id)}}); toast('Friend request sent.'); await navigate('friends'); return;}
  if (action === 'comments') {await commentsModal(id); return;}
  if (action === 'reply-comment') {
    const form = $('#comment-form');
    form.elements.parent_comment_id.value = id;
    $('#reply-context').textContent = 'Replying to ' + item.dataset.author;
    $('#reply-context').hidden = false;
    $('#comment-text').focus(); return;
  }
  if (action === 'clear-reply') {$('#comment-form').elements.parent_comment_id.value = ''; $('#reply-context').hidden = true; return;}
  if (action === 'new-review') {await reviewModal(); return;}
  if (action === 'write-review') {await reviewModal({restaurantId:id}); return;}
  if (action === 'review-visit') {await reviewModal({visitId:id}); return;}
  if (action === 'edit-review') {await reviewModal({reviewId:id}); return;}
  if (action === 'delete-review') {
    if (!window.confirm('Delete this review and its comments? Your visit record will remain.')) return;
    await api(`/api/reviews/${id}`,{method:'DELETE'});
    closeModal(); toast('Review deleted; visit retained.'); await navigate(state.page); return;
  }
}
async function submitForm(form) {
  const data = new FormData(form);
  if (form.id === 'login-form' || form.id === 'register-form') {
    const registering = form.id === 'register-form';
    if (registering && data.get('password') !== data.get('confirm_password')) throw new Error('Passwords do not match.');
    const payload = {email:String(data.get('email')).trim(),password:String(data.get('password'))};
    if (registering) payload.user_name = String(data.get('user_name')).trim();
    const {user} = await api(registering ? '/api/register' : '/api/login',{method:'POST',data:payload});
    form.reset(); await enterApp(user); return;
  }
  if (form.id === 'filter-form') {
    state.filters = {...state.filters,...Object.fromEntries(['q','suburb','cuisine','price_level','min_rating','sort'].map(key => [key,String(data.get(key) || '')]))};
    state.offsets.explore = 0; await navigate('explore'); return;
  }
  if (form.id === 'friend-search-form') {state.friendQuery = String(data.get('q') || '').trim(); await navigate('friends'); return;}
  if (form.id === 'comment-form') {
    const parent = data.get('parent_comment_id');
    await api(`/api/reviews/${form.dataset.id}/comments`,{method:'POST',data:{comment_text:String(data.get('comment_text')).trim(),parent_comment_id:parent ? Number(parent) : null}});
    toast('Comment posted.'); await commentsModal(form.dataset.id); return;
  }
  if (form.id === 'review-form') {
    const rating = Number(data.get('rating'));
    const payload = rating ? {rating,review_text:String(data.get('review_text')).trim()} : {};
    if (form.dataset.review) await api(`/api/reviews/${form.dataset.review}`,{method:'PATCH',data:payload});
    else if (form.dataset.visit) await api(`/api/visits/${form.dataset.visit}/review`,{method:'POST',data:payload});
    else await api('/api/visits',{method:'POST',data:{...payload,restaurant_id:Number(form.dataset.restaurant || data.get('restaurant_id')),visit_date:String(data.get('visit_date')),party_size:Number(data.get('party_size'))}});
    closeModal(); toast('Saved successfully.'); await navigate(state.page); return;
  }
}
document.addEventListener('click',async event => {
  const item = event.target.closest('[data-action],[data-page]');
  if (!item) return;
  if (item.dataset.action === 'close-backdrop' && event.target !== item) return;
  event.preventDefault();
  if (item.dataset.action === 'close-backdrop') {closeModal(); return;}
  item.disabled = true;
  try {
    if (item.dataset.page) {closeModal(); await navigate(item.dataset.page);}
    else await performAction(item);
  } catch (error) {toast(error.message,true);}
  finally {if (item.isConnected) item.disabled = false;}
});
document.addEventListener('submit',async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  event.preventDefault();
  const submit = form.querySelector('[type="submit"]');
  if (submit) submit.disabled = true;
  try {await submitForm(form);} catch (error) {toast(error.message,true);}
  finally {if (submit?.isConnected) submit.disabled = false;}
});
document.addEventListener('keydown', event => {if (event.key === 'Escape') closeModal();});
(async () => {try {const {user} = await api('/api/me'); await enterApp(user);} catch (error) {showAuth(); if (error.status !== 401) toast(error.message,true);}})();
