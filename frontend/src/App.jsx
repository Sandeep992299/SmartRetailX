import React, { useState, useEffect, useRef } from 'react';
import './App.css';

const GATEWAY_URL = `http://${window.location.hostname}:8000/api/v1`;
const WEBSOCKET_URL = `ws://${window.location.hostname}:8006/ws`;

const resolveProductImage = (url, name) => {
  if (url && url.startsWith('https://smartretailx-public-assets.s3.amazonaws.com/products/')) {
    return `/images/${name}.jpg`;
  }
  return url;
};

function App() {
  const [isDarkMode, setIsDarkMode] = useState(() => localStorage.getItem('sr_dark_mode') === 'true');
  const [isCardFlipped, setIsCardFlipped] = useState(false);
  const [isSplashLoading, setIsSplashLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('shop');
  const [selectedCategory, setSelectedCategory] = useState('All');

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDarkMode ? 'dark' : 'light');
    localStorage.setItem('sr_dark_mode', isDarkMode);
  }, [isDarkMode]);
  const [searchQuery, setSearchQuery] = useState('');
  const [products, setProducts] = useState([]);
  const [cart, setCart] = useState([]);
  const [orders, setOrders] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [inventory, setInventory] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [showDeveloperDock, setShowDeveloperDock] = useState(true);
  
  // Custom interactive e-commerce views
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [checkoutState, setCheckoutState] = useState('idle'); // idle | processing | success
  const [lastPlacedOrder, setLastPlacedOrder] = useState(null);
  const [selectedOrderForTracking, setSelectedOrderForTracking] = useState(null);

  // Credit Card Entry Form Modal state
  const [showPaymentForm, setShowPaymentForm] = useState(false);
  const [cardName, setCardName] = useState('');
  const [cardNumber, setCardNumber] = useState('');
  const [cardExpiry, setCardExpiry] = useState('');
  const [cardCvv, setCardCvv] = useState('');
  const [paymentErrors, setPaymentErrors] = useState('');

  // Promotional banner carousel state
  const [activeBanner, setActiveBanner] = useState(0);
  
  // Flash deal countdown timer state (2 hours 15 minutes)
  const [timeLeft, setTimeLeft] = useState(8100);

  // Loyalty Program redemptions state
  const [pointsRedeemed, setPointsRedeemed] = useState(0);
  const [redeemedCoupon, setRedeemedCoupon] = useState('');

  // Universal API error banner state
  const [apiErrorMsg, setApiErrorMsg] = useState('');

  // Auth state
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('sr_user');
    return saved ? JSON.parse(saved) : null;
  });
  const [token, setToken] = useState(() => localStorage.getItem('sr_token') || '');
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authUsername, setAuthUsername] = useState('');
  const [authRole, setAuthRole] = useState('Customer');
  const [isSignUp, setIsSignUp] = useState(false);
  const [authError, setAuthError] = useState('');

  // Profile fields state
  const [profilePic, setProfilePic] = useState(() => localStorage.getItem('sr_profile_pic') || null);
  const [profilePhone, setProfilePhone] = useState('+1 (555) 987-6543');
  const [profileAddress, setProfileAddress] = useState('456 Kubernetes Way, Pod 3, Worker Group us-west-2');

  // Admin New Product state
  const [newProdName, setNewProdName] = useState('');
  const [newProdDesc, setNewProdDesc] = useState('');
  const [newProdPrice, setNewProdPrice] = useState('');
  const [newProdCat, setNewProdCat] = useState('Electronics');
  const [newProdImage, setNewProdImage] = useState('');
  const [editingProduct, setEditingProduct] = useState(null);

  // Observability & Logs
  const [serviceHealth, setServiceHealth] = useState({
    gateway: false,
    users: false,
    products: false,
    orders: false,
    payments: false,
    inventory: false,
    notifications: false
  });
  const [gatewayLatency, setGatewayLatency] = useState(0);
  const [logs, setLogs] = useState([]);
  
  const wsRef = useRef(null);

  // Checks if active user has administrator privileges
  const isAuthorized = user && (user.role === 'Admin' || user.role === 'Manager');

  // Splash Screen Timer
  useEffect(() => {
    const timer = setTimeout(() => {
      setIsSplashLoading(false);
    }, 2000);
    return () => clearTimeout(timer);
  }, []);

  // Flash Deals Countdown Timer
  useEffect(() => {
    const timer = setInterval(() => {
      setTimeLeft(prev => (prev > 0 ? prev - 1 : 8100));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Banner autoplay interval
  useEffect(() => {
    const bannerTimer = setInterval(() => {
      setActiveBanner(prev => (prev + 1) % 3);
    }, 5000);
    return () => clearInterval(bannerTimer);
  }, []);

  const addLog = (message, type = 'info') => {
    const timeStr = new Date().toLocaleTimeString();
    setLogs(prev => [`[${timeStr}] ${message}`, ...prev].slice(0, 50));
  };

  // Connect WebSockets
  useEffect(() => {
    const connectWS = () => {
      addLog("Connecting to Live Event broker...", "info");
      const ws = new WebSocket(WEBSOCKET_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        addLog("Notification stream WebSocket active.", "info");
        setServiceHealth(prev => ({ ...prev, notifications: true }));
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === 'ping') return;

          addLog(`Kafka message received: ${payload.event_type}`, "warn");

          const newNotif = {
            id: payload.event_id || Date.now(),
            type: payload.event_type,
            title: payload.event_type.replace(/-/g, ' ').toUpperCase(),
            message: getEventMessage(payload),
            timestamp: new Date().toLocaleTimeString()
          };
          setNotifications(prev => [newNotif, ...prev].slice(0, 30));

          if (payload.event_type === 'payment-settled' || payload.event_type === 'order-created') {
            fetchOrders();
            fetchInventory();
          }
        } catch (err) {
          console.error("Error reading websocket", err);
        }
      };

      ws.onclose = () => {
        setServiceHealth(prev => ({ ...prev, notifications: false }));
        setTimeout(connectWS, 5000);
      };

      ws.onerror = () => {
        setServiceHealth(prev => ({ ...prev, notifications: false }));
      };
    };

    connectWS();

    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const getEventMessage = (payload) => {
    const data = payload.data || {};
    switch (payload.event_type) {
      case 'order-created':
        return `Order #${data.order_id} placed for $${data.total_amount.toFixed(2)}`;
      case 'payment-settled':
        return `Payment received for Order #${data.order_id}. Ledger committed to PostgreSQL.`;
      case 'payment-failed':
        return `Payment failed for Order #${data.order_id}. Compensation rollback triggered.`;
      case 'low-stock-alert':
        return `Low stock alert: "${data.product_name}" is down to ${data.stock_count} units!`;
      case 'inventory-restocked':
        return `Stock replenished: "${data.product_name}" count is now ${data.stock_count}.`;
      default:
        return JSON.stringify(data);
    }
  };

  useEffect(() => {
    fetchProducts();
    fetchOrders();
    fetchInventory();
    fetchTransactions();
    
    const interval = setInterval(probeHealth, 5000);
    probeHealth();
    
    return () => clearInterval(interval);
  }, [token]);

  // Sync selected order for tracking to reflect live database updates
  useEffect(() => {
    if (selectedOrderForTracking) {
      const liveOrder = orders.find(o => o.id === selectedOrderForTracking.id);
      if (liveOrder) {
        setSelectedOrderForTracking(liveOrder);
      }
    }
  }, [orders]);

  const fetchHeaders = () => {
    const headers = { 'Content-Type': 'application/json' };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
  };

  const gatewayFetch = async (endpoint, options = {}) => {
    const start = performance.now();
    try {
      const res = await fetch(`${GATEWAY_URL}${endpoint}`, {
        ...options,
        headers: { ...fetchHeaders(), ...options.headers }
      });
      const end = performance.now();
      setGatewayLatency(end - start);
      
      const latencyHeader = res.headers.get("X-Gateway-Latency-Seconds");
      if (latencyHeader) {
        addLog(`Proxy latency for ${endpoint}: ${parseFloat(latencyHeader) * 1000} ms`, "info");
      }
      
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Error code ${res.status}`);
      }
      return await res.json();
    } catch (err) {
      setApiErrorMsg(`Microservices API error on ${endpoint}: ${err.message}. Please verify service clusters.`);
      addLog(`API error on ${endpoint}: ${err.message}`, "error");
      throw err;
    }
  };

  const probeHealth = async () => {
    try {
      const res = await fetch(`http://${window.location.hostname}:8000/healthz`);
      const data = await res.json();
      setServiceHealth(prev => ({ ...prev, gateway: data.status === 'healthy' }));
      
      probeServiceHealth('users', 8001);
      probeServiceHealth('products', 8002);
      probeServiceHealth('orders', 8003);
      probeServiceHealth('payments', 8004);
      probeServiceHealth('inventory', 8005);
    } catch (e) {
      setServiceHealth(prev => ({
        gateway: false, users: false, products: false, orders: false, payments: false, inventory: false
      }));
    }
  };

  const probeServiceHealth = async (name, port) => {
    try {
      const res = await fetch(`http://${window.location.hostname}:${port}/${name}/healthz`);
      setServiceHealth(prev => ({ ...prev, [name]: res.ok }));
    } catch (e) {
      setServiceHealth(prev => ({ ...prev, [name]: false }));
    }
  };

  const fetchProducts = async () => {
    try {
      const data = await gatewayFetch('/products');
      setProducts(data);
      setApiErrorMsg('');
    } catch (e) {}
  };

  const fetchOrders = async () => {
    if (!token) return;
    try {
      const data = await gatewayFetch('/orders');
      setOrders(data);
    } catch (e) {}
  };

  const fetchTransactions = async () => {
    if (!token || !isAuthorized) return;
    try {
      const data = await gatewayFetch('/payments/transactions');
      setTransactions(data);
    } catch (e) {}
  };

  const fetchInventory = async () => {
    try {
      const data = await gatewayFetch('/inventory');
      setInventory(data);
    } catch (e) {}
  };

  const handleAuthSubmit = async (e) => {
    e.preventDefault();
    setAuthError('');
    try {
      if (isSignUp) {
        await fetch(`http://${window.location.hostname}:8001/users/signup`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: authUsername,
            email: authEmail,
            password: authPassword,
            role: authRole
          })
        });
        addLog(`Registered user: ${authUsername}`, "info");
        setIsSignUp(false);
        setAuthPassword('');
      } else {
        const res = await fetch(`http://${window.location.hostname}:8001/users/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: authEmail,
            password: authPassword
          })
        });
        if (!res.ok) throw new Error("Incorrect email or password");
        const data = await res.json();
        
        localStorage.setItem('sr_token', data.access_token);
        localStorage.setItem('sr_user', JSON.stringify({
          username: data.username,
          role: data.role,
          email: data.email
        }));
        
        setToken(data.access_token);
        setUser({ username: data.username, role: data.role, email: data.email });
        setPointsRedeemed(0); // reset redemptions
        addLog(`Sign in successful. User: ${data.username}`, "info");
        setActiveTab('shop');
      }
    } catch (err) {
      setAuthError(err.message);
      addLog(`Sign in error: ${err.message}`, "error");
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('sr_token');
    localStorage.removeItem('sr_user');
    setToken('');
    setUser(null);
    setOrders([]);
    setTransactions([]);
    addLog("User logged out.", "info");
    setActiveTab('shop');
  };

  const addToCart = (product) => {
    setCart(prev => {
      const existing = prev.find(item => item.product_id === product.id);
      if (existing) {
        return prev.map(item => 
          item.product_id === product.id ? { ...item, quantity: item.quantity + 1 } : item
        );
      }
      return [...prev, {
        product_id: product.id,
        product_name: product.name,
        price: product.price,
        quantity: 1
      }];
    });
    addLog(`Added to cart: "${product.name}"`, "info");
  };

  const removeFromCart = (productId) => {
    setCart(prev => prev.filter(item => item.product_id !== productId));
  };

  const handleCardNumberChange = (e) => {
    let value = e.target.value.replace(/\D/g, '');
    value = value.substring(0, 16);
    const parts = [];
    for (let i = 0; i < value.length; i += 4) {
      parts.push(value.substring(i, i + 4));
    }
    setCardNumber(parts.join(' '));
  };

  const handleExpiryChange = (e) => {
    let value = e.target.value.replace(/\D/g, '');
    value = value.substring(0, 4);
    if (value.length > 2) {
      setCardExpiry(value.substring(0, 2) + '/' + value.substring(2));
    } else {
      setCardExpiry(value);
    }
  };

  const handleCvvChange = (e) => {
    let value = e.target.value.replace(/\D/g, '');
    setCardCvv(value.substring(0, 3));
  };

  const startCheckoutFlow = () => {
    if (!token) {
      setActiveTab('user');
      addLog("Checkout failed: Please sign in.", "warn");
      return;
    }
    setPaymentErrors('');
    setShowPaymentForm(true);
  };

  const checkoutCart = async (e) => {
    e.preventDefault();
    setPaymentErrors('');

    // Client-side form validations
    const cleanCard = cardNumber.replace(/\s/g, '');
    if (cleanCard.length !== 16) {
      setPaymentErrors("Card number must be exactly 16 digits.");
      return;
    }
    if (cardExpiry.length !== 5) {
      setPaymentErrors("Expiry date must be in MM/YY format.");
      return;
    }
    if (cardCvv.length !== 3) {
      setPaymentErrors("CVV must be exactly 3 digits.");
      return;
    }

    setShowPaymentForm(false);
    
    // Trigger the interactive processing screen
    setCheckoutState('processing');
    addLog("Securing payment details... Uploading encrypted tokens to PG payment gateway.", "info");

    try {
      const orderRes = await gatewayFetch('/orders', {
        method: 'POST',
        body: JSON.stringify({ items: cart })
      });
      
      // Delay to show credit card spinning processing animation
      setTimeout(() => {
        setCheckoutState('success');
        setLastPlacedOrder(orderRes);
        setCart([]);
        fetchOrders();
        // Clear card forms
        setCardName('');
        setCardNumber('');
        setCardExpiry('');
        setCardCvv('');
        addLog("Payment transaction settled successfully via secure MSK channel.", "info");
      }, 2500);

    } catch (e) {
      setCheckoutState('idle');
      addLog(`Checkout error: {e.message}`, "error");
    }
  };

  const handleProductSubmit = async (e) => {
    e.preventDefault();
    try {
      const imgUrl = newProdImage || `https://smartretailx-public-assets.s3.amazonaws.com/products/generic-item.jpg`;
      
      if (editingProduct) {
        await gatewayFetch(`/products/${editingProduct.id}`, {
          method: 'PUT',
          body: JSON.stringify({
            name: newProdName,
            description: newProdDesc,
            price: parseFloat(newProdPrice),
            category: newProdCat,
            image_url: imgUrl
          })
        });
        addLog(`Product "${newProdName}" updated successfully.`, "info");
        setEditingProduct(null);
      } else {
        await gatewayFetch('/products', {
          method: 'POST',
          body: JSON.stringify({
            name: newProdName,
            description: newProdDesc,
            price: parseFloat(newProdPrice),
            category: newProdCat,
            image_url: imgUrl
          })
        });
        addLog("New product saved in catalogue.", "info");
      }
      setNewProdName('');
      setNewProdDesc('');
      setNewProdPrice('');
      setNewProdImage('');
      setNewProdCat('Electronics');
      fetchProducts();
    } catch (e) {}
  };

  const startEditing = (p) => {
    setEditingProduct(p);
    setNewProdName(p.name);
    setNewProdDesc(p.description || '');
    setNewProdPrice(p.price);
    setNewProdCat(p.category);
    setNewProdImage(p.image_url || '');
    addLog(`Loaded product "${p.name}" for editing.`, "info");
  };

  const cancelEditing = () => {
    setEditingProduct(null);
    setNewProdName('');
    setNewProdDesc('');
    setNewProdPrice('');
    setNewProdImage('');
    setNewProdCat('Electronics');
  };

  const handleDeleteProduct = async (id) => {
    if (!confirm("Are you sure you want to delete this product?")) return;
    try {
      await gatewayFetch(`/products/${id}`, { method: 'DELETE' });
      addLog(`Catalog item deleted: ${id}`, "info");
      if (editingProduct && editingProduct.id === id) {
        cancelEditing();
      }
      fetchProducts();
    } catch (e) {}
  };

  const handleUpdateStock = async (id, currentStock) => {
    const qty = prompt("Enter new inventory stock level:", currentStock);
    if (qty === null || isNaN(qty)) return;
    try {
      await gatewayFetch(`/inventory/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ stock_count: parseInt(qty) })
      });
      addLog(`Stock quantity of Product ID ${id} set to ${qty}.`, "info");
      fetchInventory();
    } catch (e) {}
  };

  const applyQuickAuth = (role) => {
    if (role === 'Admin') {
      setAuthEmail('admin@smartretailx.com');
      setAuthPassword('AdminPass123!');
      setAuthUsername('admin');
      setAuthRole('Admin');
    } else if (role === 'Manager') {
      setAuthEmail('manager@smartretailx.com');
      setAuthPassword('ManagerPass123!');
      setAuthUsername('manager');
      setAuthRole('Manager');
    } else {
      setAuthEmail('customer@smartretailx.com');
      setAuthPassword('CustomerPass123!');
      setAuthUsername('customer');
      setAuthRole('Customer');
    }
    setIsSignUp(false);
  };

  const handleProfilePhotoUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setProfilePic(reader.result);
        localStorage.setItem('sr_profile_pic', reader.result);
        addLog("Profile picture updated.", "info");
      };
      reader.readAsDataURL(file);
    }
  };

  const handleProductImageUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setNewProdImage(reader.result);
        // Map to S3 architecture path log
        const cleanName = file.name.toLowerCase().replace(/[^a-z0-9.]/g, '-');
        addLog(`[S3] Uploading asset "${file.name}" to AWS S3 bucket: s3://smartretailx-public-assets/products/${cleanName}`, "info");
        addLog(`[S3] Public asset address registered: https://smartretailx-public-assets.s3.amazonaws.com/products/${cleanName}`, "info");
      };
      reader.readAsDataURL(file);
    }
  };

  // Filter products based on Category and Search Query
  const filteredProducts = products.filter(p => {
    const matchesCategory = selectedCategory === 'All' || p.category.toLowerCase() === selectedCategory.toLowerCase();
    const matchesSearch = p.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          (p.description && p.description.toLowerCase().includes(searchQuery.toLowerCase()));
    return matchesCategory && matchesSearch;
  });

  // Calculate Loyalty points dynamically (1 point per dollar spent on completed orders + starting seed - points redeemed)
  const totalSpent = orders
    .filter(o => o.status === 'Paid' || o.status === 'success')
    .reduce((sum, o) => sum + o.total_amount, 0);
  const basePoints = Math.floor(totalSpent) + (user ? 120 : 0);
  const loyaltyPoints = Math.max(0, basePoints - pointsRedeemed);

  // Redeem rewards logic
  const handleRedeemReward = (cost, code) => {
    if (loyaltyPoints < cost) {
      alert("Insufficient points! Shop more to earn loyalty points.");
      return;
    }
    setPointsRedeemed(prev => prev + cost);
    setRedeemedCoupon(code);
    addLog(`Redeemed ${cost} loyalty points for coupon: ${code}`, "info");
    alert(`Reward Redeemed Successfully!\nYour Coupon Code: ${code}\nThis code has been copied to your console logs.`);
  };

  // Recommendations logic (Affinity categories matching items currently in Cart or Order history)
  const getRecommendations = () => {
    if (products.length === 0) return [];
    
    // Identify categories with user affinity
    const affinityCategories = new Set(
      cart.map(item => {
        const prod = products.find(p => p.id === item.product_id);
        return prod ? prod.category : null;
      }).filter(Boolean)
    );

    // If affinity is empty, fallback to trending electronics and premium furniture
    if (affinityCategories.size === 0) {
      return products.slice(0, 3);
    }

    // Return products in affinity categories that are NOT already in the cart
    const recommended = products.filter(p => 
      affinityCategories.has(p.category) && 
      !cart.some(c => c.product_id === p.id)
    );

    return recommended.length > 0 ? recommended.slice(0, 3) : products.slice(0, 3);
  };

  // Format Countdown Timer
  const formatTimer = (seconds) => {
    const h = String(Math.floor(seconds / 3600)).padStart(2, '0');
    const m = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0');
    const s = String(seconds % 60).padStart(2, '0');
    return `${h}h : ${m}m : ${s}s`;
  };

  // Render Splash Loader
  if (isSplashLoading) {
    return (
      <div className="splash-screen">
        <h1 className="splash-logo">Smart<span>RetailX</span></h1>
        <div className="splash-loader-bar">
          <div className="splash-loader-progress"></div>
        </div>
        <p style={{marginTop: '16px', fontSize: '14px', color: 'var(--text-muted)'}}>Launching e-commerce system...</p>
      </div>
    );
  }

  return (
    <div className="app-container">
      
      {/* Universal API Error Banner */}
      {apiErrorMsg && (
        <div style={{backgroundColor: 'var(--accent)', color: 'white', padding: '10px 24px', textAlign: 'center', fontSize: '13px', fontWeight: '600', position: 'sticky', top: 0, zIndex: 2000, boxShadow: 'var(--shadow-md)', display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
          <span>⚠️ {apiErrorMsg}</span>
          <button onClick={() => setApiErrorMsg('')} style={{background: 'none', border: 'none', color: 'white', fontWeight: 'bold', cursor: 'pointer', fontSize: '16px'}}>✕</button>
        </div>
      )}

      {/* Top E-Commerce Header Panel */}
      <header className="app-header">
        <div className="header-top">
          <div className="brand-section">
            <h1 className="brand-logo" style={{cursor: 'pointer'}} onClick={() => { setActiveTab('shop'); setSelectedCategory('All'); setSearchQuery(''); }}>
              Smart<span>RetailX</span>
            </h1>
          </div>
          
          {/* E-Commerce Search Bar */}
          <div className="search-container">
            <input 
              type="text" 
              placeholder="Search premium electronics, apparel, furniture..." 
              className="search-input"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
            />
            <button className="search-button">Search</button>
          </div>

          <div className="header-actions">
            <button className="theme-toggle-btn" onClick={() => setIsDarkMode(!isDarkMode)} style={{fontSize: '20px', border: 'none', background: 'none', cursor: 'pointer', padding: '8px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', marginRight: '4px'}} title={isDarkMode ? "Switch to Light Mode" : "Switch to Dark Mode"}>
              {isDarkMode ? '🌙' : '☀️'}
            </button>
            <button className="action-item" onClick={() => setActiveTab('cart')}>
              <span className="action-icon">🛒</span>
              <span>Cart</span>
              {cart.length > 0 && <span className="cart-badge">{cart.reduce((sum, item) => sum + item.quantity, 0)}</span>}
            </button>
            <button className="action-item" onClick={() => setActiveTab('orders')}>
              <span className="action-icon">📦</span>
              <span>Orders</span>
            </button>
            
            <div className="user-info-widget">
              {user ? (
                <>
                  {/* Global Loyalty Points Badge */}
                  <span style={{backgroundColor: 'gold', color: '#855d00', padding: '4px 10px', borderRadius: '12px', fontSize: '12px', fontWeight: '800', marginRight: '8px', boxShadow: '0 2px 4px rgba(218,165,32,0.2)', display: 'flex', alignItems: 'center', gap: '4px'}}>
                    ✨ {loyaltyPoints} pts
                  </span>

                  {profilePic ? (
                    <img src={profilePic} alt="Avatar" style={{width: '36px', height: '36px', borderRadius: '50%', objectFit: 'cover', border: '1px solid var(--primary)'}} />
                  ) : (
                    <div className="user-avatar">{user.username.substring(0,2).toUpperCase()}</div>
                  )}
                  <div className="user-text" style={{cursor: 'pointer'}} onClick={() => setActiveTab('user')}>
                    <span className="user-name">{user.username}</span>
                    <span className="user-role">{user.role}</span>
                  </div>
                  <button className="btn-secondary" onClick={handleLogout} style={{padding: '6px 12px', fontSize: '11px', marginLeft: '6px'}}>Logout</button>
                </>
              ) : (
                <button className="btn-primary" onClick={() => setActiveTab('user')}>Sign In</button>
              )}
            </div>
          </div>
        </div>

        {/* E-Commerce Category Filter Tabs */}
        <div className="categories-nav">
          {['All', 'Electronics', 'Furniture', 'Apparel', 'Outdoor'].map(cat => (
            <button 
              key={cat} 
              className={`category-tab ${selectedCategory === cat ? 'active' : ''}`}
              onClick={() => { setSelectedCategory(cat); setActiveTab('shop'); }}
            >
              {cat}
            </button>
          ))}
        </div>
      </header>

      {/* Main Container Layout */}
      <div className="main-layout">
        {/* Left Sidebar Menu */}
        <nav className="sidebar-panel">
          <span className="sidebar-heading">Shopping Menu</span>
          <button className={`sidebar-item ${activeTab === 'shop' ? 'active' : ''}`} onClick={() => setActiveTab('shop')}>
            🛍️ Store Catalogue
          </button>
          <button className={`sidebar-item ${activeTab === 'cart' ? 'active' : ''}`} onClick={() => setActiveTab('cart')}>
            🛒 Cart ({cart.reduce((sum, item) => sum + item.quantity, 0)})
          </button>
          <button className={`sidebar-item ${activeTab === 'orders' ? 'active' : ''}`} onClick={() => { setActiveTab('orders'); setSelectedOrderForTracking(null); }}>
            📦 My Orders ({orders.length})
          </button>
          
          {/* Admin tabs - ONLY visible to logged-in Admins/Managers */}
          {isAuthorized && (
            <>
              <span className="sidebar-heading" style={{marginTop: '12px'}}>Management</span>
              <button className={`sidebar-item ${activeTab === 'management' ? 'active' : ''}`} onClick={() => setActiveTab('management')}>
                ⚙️ Inventory & Catalogue
              </button>
              <button className={`sidebar-item ${activeTab === 'observability' ? 'active' : ''}`} onClick={() => setActiveTab('observability')}>
                📈 Telemetry & Logs
              </button>
            </>
          )}
          
          <span className="sidebar-heading" style={{marginTop: '12px'}}>Profile Settings</span>
          <button className={`sidebar-item ${activeTab === 'user' ? 'active' : ''}`} onClick={() => setActiveTab('user')}>
            🔑 Account Profile
          </button>
        </nav>

        {/* Middle Main Content Screen */}
        <main className="shop-content">
          {activeTab === 'shop' && (
            <>
              {/* E-Commerce Promotional Banner Carousel */}
              <div className="promo-banner" style={{position: 'relative', overflow: 'hidden', padding: '30px 40px', background: 'linear-gradient(135deg, #ff5000 0%, #ff8c00 100%)', borderRadius: '16px', color: 'white', minHeight: '160px', display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
                {activeBanner === 0 && (
                  <div className="banner-slide fade-in">
                    <div style={{fontSize: '11px', textTransform: 'uppercase', letterSpacing: '2px', opacity: 0.8, fontWeight: '700'}}>🔥 Summer Tech Carnival</div>
                    <div className="promo-title" style={{fontSize: '28px', marginTop: '6px'}}>Get up to 50% discount!</div>
                    <div className="promo-desc" style={{opacity: 0.95, fontSize: '13px', marginTop: '4px'}}>
                      Save big on smart noise-canceling headphones, customizable mechanical keyboards, and premium outdoor accessories. Free global shipping!
                    </div>
                  </div>
                )}
                {activeBanner === 1 && (
                  <div className="banner-slide fade-in">
                    <div style={{fontSize: '11px', textTransform: 'uppercase', letterSpacing: '2px', opacity: 0.8, fontWeight: '700'}}>✨ Loyalty Points Program</div>
                    <div className="promo-title" style={{fontSize: '28px', marginTop: '6px'}}>Double Points Week!</div>
                    <div className="promo-desc" style={{opacity: 0.95, fontSize: '13px', marginTop: '4px'}}>
                      Earn 2 loyalty points for every $1 spent on apparel and lifestyle items. Log in to check your account point totals and redeem vouchers!
                    </div>
                  </div>
                )}
                {activeBanner === 2 && (
                  <div className="banner-slide fade-in">
                    <div style={{fontSize: '11px', textTransform: 'uppercase', letterSpacing: '2px', opacity: 0.8, fontWeight: '700'}}>🎁 Member Exclusives</div>
                    <div className="promo-title" style={{fontSize: '28px', marginTop: '6px'}}>Free Shipping Vouchers</div>
                    <div className="promo-desc" style={{opacity: 0.95, fontSize: '13px', marginTop: '4px'}}>
                      Redeem shipping coupons for just 100 points. Check out the reward redemption table inside your profile portal.
                    </div>
                  </div>
                )}

                {/* Dots indicators */}
                <div style={{position: 'absolute', bottom: '15px', right: '20px', display: 'flex', gap: '6px'}}>
                  {[0, 1, 2].map(idx => (
                    <span 
                      key={idx} 
                      onClick={() => setActiveBanner(idx)}
                      style={{
                        width: '8px', 
                        height: '8px', 
                        borderRadius: '50%', 
                        backgroundColor: activeBanner === idx ? 'white' : 'rgba(255,255,255,0.4)', 
                        cursor: 'pointer',
                        transition: 'var(--transition-smooth)'
                      }}
                    />
                  ))}
                </div>
              </div>

              {/* Dynamic Recommendations Shelf (Product affinity) */}
              {products.length > 0 && (
                <div style={{margin: '24px 0'}}>
                  <h3 style={{fontSize: '17px', fontWeight: '800', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--neutral-dark)'}}>
                    🎯 Recommended For You
                    <span style={{fontSize: '11px', color: 'var(--text-muted)', fontWeight: 'normal'}}>(Based on your interests)</span>
                  </h3>
                  <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px'}}>
                    {getRecommendations().map(p => (
                      <div key={`rec-${p.id}`} onClick={() => setSelectedProduct(p)} style={{display: 'flex', gap: '12px', padding: '12px', background: '#ffffff', border: '1px solid var(--border-color)', borderRadius: '12px', cursor: 'pointer', transition: 'var(--transition-smooth)', boxShadow: 'var(--shadow-sm)'}} className="rec-card-hover">
                        <img src={resolveProductImage(p.image_url, p.name)} alt={p.name} style={{width: '60px', height: '60px', objectFit: 'cover', borderRadius: '8px'}} />
                        <div style={{display: 'flex', flexDirection: 'column', justifyContent: 'center', overflow: 'hidden'}}>
                          <div style={{fontSize: '12px', fontWeight: '700', color: 'var(--neutral-dark)', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap', width: '100%'}}>{p.name}</div>
                          <div style={{fontSize: '13px', color: 'var(--primary)', fontWeight: '800', marginTop: '4px'}}>${p.price.toFixed(2)}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Ticking Flash Sale deals bar */}
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#fff', padding: '14px 20px', borderRadius: '12px', border: '1px solid var(--border-color)', marginBottom: '24px', boxShadow: 'var(--shadow-sm)'}}>
                <div style={{display: 'flex', alignItems: 'center', gap: '10px'}}>
                  <span style={{fontSize: '20px'}}>⏰</span>
                  <div>
                    <strong style={{fontSize: '14px', color: 'var(--neutral-dark)'}}>SmartRetailX Flash Deals</strong>
                    <div style={{fontSize: '11px', color: 'var(--text-muted)'}}>Limited quantities. Grab them before they sell out!</div>
                  </div>
                </div>
                <div style={{display: 'flex', alignItems: 'center', gap: '8px'}}>
                  <span style={{fontSize: '12px', color: 'var(--text-muted)', fontWeight: '600'}}>Ends In:</span>
                  <span style={{backgroundColor: 'var(--primary)', color: 'white', padding: '6px 12px', borderRadius: '8px', fontSize: '13px', fontFamily: 'monospace', fontWeight: '800'}}>
                    {formatTimer(timeLeft)}
                  </span>
                </div>
              </div>

              <div className="content-header">
                <div className="content-title">{selectedCategory} Catalog</div>
                <span style={{fontSize: '13px', color: 'var(--text-muted)'}}>{filteredProducts.length} items found</span>
              </div>
              
              {filteredProducts.length === 0 ? (
                <div style={{textAlign: 'center', padding: '60px 0'}}>
                  <span style={{fontSize: '48px'}}>🔍</span>
                  <p style={{color: 'var(--text-secondary)', marginTop: '16px'}}>No products found matching your search criteria.</p>
                </div>
              ) : (
                <div className="store-grid">
                  {filteredProducts.map(p => {
                    const stockItem = inventory.find(i => i.product_id === p.id);
                    const isOutOfStock = stockItem && stockItem.stock_count <= 0;
                    return (
                      <div className="store-card" key={p.id} onClick={() => setSelectedProduct(p)}>
                        <div className="store-image-wrapper">
                          <img src={resolveProductImage(p.image_url, p.name)} alt={p.name} className="store-image" />
                          {p.price > 100 && <span className="discount-tag">Hot Sale</span>}
                        </div>
                        <div className="store-card-info">
                          <span className="store-card-category">{p.category}</span>
                          <h3 className="store-card-name" title={p.name}>{p.name}</h3>
                          
                          <div className="rating-stars">
                            <span>★</span><span>★</span><span>★</span><span>★</span><span>☆</span>
                            <span style={{color: 'var(--text-muted)', fontSize: '11px', marginLeft: '4px'}}>(4.5)</span>
                          </div>
                          
                          <div className="store-card-footer" onClick={e => e.stopPropagation()}>
                            <span className="store-card-price">${p.price.toFixed(2)}</span>
                            <button 
                              className="btn-primary" 
                              onClick={() => addToCart(p)}
                              disabled={isOutOfStock}
                              style={{padding: '8px 14px', fontSize: '12px'}}
                            >
                              {isOutOfStock ? 'Sold Out' : 'Buy'}
                            </button>
                          </div>
                          {stockItem && (
                            <div style={{fontSize: '11px', color: stockItem.stock_count < 5 ? 'var(--accent)' : 'var(--text-muted)', marginTop: '4px'}}>
                              Stock: {stockItem.stock_count} units {stockItem.stock_count < 5 && '(Low Stock!)'}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}

          {activeTab === 'cart' && (
            <>
              <div className="content-header">
                <div className="content-title">My Shopping Cart</div>
              </div>
              
              {cart.length === 0 ? (
                <div style={{textAlign: 'center', padding: '60px 0'}}>
                  <span style={{fontSize: '64px'}}>🛒</span>
                  <p style={{color: 'var(--text-secondary)', marginTop: '20px', fontSize: '16px'}}>Your shopping cart is empty.</p>
                  <button className="btn-primary" onClick={() => setActiveTab('shop')} style={{marginTop: '20px'}}>Go Shopping</button>
                </div>
              ) : (
                <div className="cart-table-wrapper">
                  {cart.map(item => (
                    <div className="cart-row" key={item.product_id}>
                      <div className="cart-row-details">
                        <span className="cart-row-name">{item.product_name}</span>
                        <span className="cart-row-price">{item.quantity} × ${item.price.toFixed(2)}</span>
                      </div>
                      <div style={{display: 'flex', alignItems: 'center', gap: '24px'}}>
                        <span style={{fontWeight: '800', fontSize: '18px'}}>${(item.quantity * item.price).toFixed(2)}</span>
                        <button className="btn-accent" onClick={() => removeFromCart(item.product_id)}>Remove</button>
                      </div>
                    </div>
                  ))}
                  
                  <div className="cart-summary-section">
                    <span style={{fontWeight: '700', fontSize: '18px'}}>Total Order Amount:</span>
                    <span className="cart-grand-total">
                      ${cart.reduce((sum, item) => sum + (item.quantity * item.price), 0).toFixed(2)}
                    </span>
                  </div>

                  <div style={{marginTop: '24px', display: 'flex', gap: '16px', justifyContent: 'flex-end'}}>
                    <button className="btn-secondary" onClick={() => setCart([])}>Clear Cart</button>
                    <button className="btn-primary" onClick={startCheckoutFlow}>Proceed to Checkout</button>
                  </div>
                </div>
              )}
            </>
          )}

          {activeTab === 'orders' && (
            <>
              <div className="content-header">
                <div className="content-title">Order Status & Tracking</div>
              </div>
              
              {!token ? (
                <p style={{color: 'var(--text-secondary)'}}>Please sign in to view your orders.</p>
              ) : orders.length === 0 ? (
                <p style={{color: 'var(--text-secondary)'}}>No orders found.</p>
              ) : (
                <div style={{display: 'flex', flexDirection: 'column', gap: '24px'}}>
                  <table className="orders-table">
                    <thead>
                      <tr>
                        <th>Order ID</th>
                        <th>Total Amount</th>
                        <th>Created At</th>
                        <th>Status</th>
                        <th>Tracking</th>
                      </tr>
                    </thead>
                    <tbody>
                      {orders.map(o => (
                        <tr key={o.id}>
                          <td><strong>#{o.id.substring(o.id.length - 8)}</strong></td>
                          <td>${o.total_amount.toFixed(2)}</td>
                          <td>{new Date(o.created_at).toLocaleString()}</td>
                          <td>
                            <span className={`status-badge ${o.status.toLowerCase()}`}>
                              {o.status}
                            </span>
                          </td>
                          <td>
                            <button className="btn-secondary" onClick={() => setSelectedOrderForTracking(o)} style={{padding: '4px 10px', fontSize: '11px'}}>
                              Track Status 🚚
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {/* Dynamic Visual Stepper Timeline for Order Tracking - BACKED BY LIVE DB STATUS */}
                  {selectedOrderForTracking && (
                    <div style={{border: '1px solid var(--border-color)', borderRadius: '16px', padding: '24px', background: '#f8fafc', marginTop: '20px'}}>
                      <h4 style={{fontSize: '16px', marginBottom: '16px'}}>Live Tracking Timeline for Order <strong>#{selectedOrderForTracking.id}</strong></h4>
                      
                      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', position: 'relative', padding: '10px 0'}}>
                        <div style={{position: 'absolute', left: '12.5%', right: '12.5%', height: '4px', backgroundColor: '#e2e8f0', zIndex: '1', top: '22px'}}>
                          <div style={{
                            width: selectedOrderForTracking.status === 'Paid' || selectedOrderForTracking.status === 'success' ? '100%' : '0%',
                            height: '100%',
                            backgroundColor: 'var(--secondary)',
                            transition: 'width 0.5s ease'
                          }}></div>
                        </div>

                        {/* Step 1: Order Created (MongoDB) */}
                        <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', zIndex: '2', width: '25%'}}>
                          <div style={{width: '28px', height: '28px', borderRadius: '50%', backgroundColor: 'var(--secondary)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '12px', fontWeight: '700', lineHeight: '28px'}}>✓</div>
                          <span style={{fontSize: '12px', fontWeight: '700', marginTop: '8px'}}>Order Created</span>
                          <span style={{fontSize: '10px', color: 'var(--text-muted)'}}>Saved in MongoDB</span>
                        </div>

                        {/* Step 2: Payment Confirmed (PostgreSQL) */}
                        <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', zIndex: '2', width: '25%'}}>
                          <div className={selectedOrderForTracking.status === 'Pending' ? 'pulse-avatar' : ''} style={{
                            width: '28px', height: '28px', borderRadius: '50%',
                            backgroundColor: selectedOrderForTracking.status === 'Paid' || selectedOrderForTracking.status === 'success' ? 'var(--secondary)' : '#e2e8f0',
                            color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '12px', fontWeight: '700'
                          }}>{selectedOrderForTracking.status === 'Paid' || selectedOrderForTracking.status === 'success' ? '✓' : '2'}</div>
                          <span style={{fontSize: '12px', fontWeight: '700', marginTop: '8px'}}>Payment Confirmed</span>
                          <span style={{fontSize: '10px', color: 'var(--text-muted)', textAlign: 'center'}}>
                            {selectedOrderForTracking.status === 'Paid' || selectedOrderForTracking.status === 'success' ? 'Settled in PostgreSQL' : 'Processing PG Settlement...'}
                          </span>
                        </div>

                        {/* Step 3: Inventory Reserved (Redis) */}
                        <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', zIndex: '2', width: '25%'}}>
                          <div style={{
                            width: '28px', height: '28px', borderRadius: '50%',
                            backgroundColor: selectedOrderForTracking.status === 'Paid' || selectedOrderForTracking.status === 'success' ? 'var(--secondary)' : '#e2e8f0',
                            color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '12px', fontWeight: '700'
                          }}>{selectedOrderForTracking.status === 'Paid' || selectedOrderForTracking.status === 'success' ? '✓' : '3'}</div>
                          <span style={{fontSize: '12px', fontWeight: '700', marginTop: '8px'}}>Inventory Reserved</span>
                          <span style={{fontSize: '10px', color: 'var(--text-muted)', textAlign: 'center'}}>
                            {selectedOrderForTracking.status === 'Paid' || selectedOrderForTracking.status === 'success' ? 'Allocated in Redis' : 'Awaiting Settlement'}
                          </span>
                        </div>

                        {/* Step 4: Dispatched (Shipping) */}
                        <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', zIndex: '2', width: '25%'}}>
                          <div style={{
                            width: '28px', height: '28px', borderRadius: '50%',
                            backgroundColor: selectedOrderForTracking.status === 'Paid' || selectedOrderForTracking.status === 'success' ? 'var(--primary)' : '#e2e8f0',
                            color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '12px', fontWeight: '700'
                          }}>🚚</div>
                          <span style={{fontSize: '12px', fontWeight: '700', marginTop: '8px'}}>Shipping</span>
                          <span style={{fontSize: '10px', color: 'var(--text-muted)', textAlign: 'center'}}>
                            {selectedOrderForTracking.status === 'Paid' || selectedOrderForTracking.status === 'success' ? 'Dispatched' : 'Awaiting Payment'}
                          </span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {activeTab === 'management' && isAuthorized && (
            <>
              <div className="content-header">
                <div className="content-title">Catalogue and Inventory Administration</div>
              </div>
              <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px'}}>
                {/* Product Creation / Edit Form */}
                <form onSubmit={handleProductSubmit} className="auth-box" style={{margin: '0', maxWidth: '100%', boxShadow: 'none', border: '1px solid var(--border-color)', background: '#f8fafc'}}>
                  <h3>{editingProduct ? 'Edit Catalog Item' : 'Add New Catalog Item'}</h3>
                  <div className="form-group">
                    <label>Product Name</label>
                    <input type="text" className="form-input" value={newProdName} onChange={e => setNewProdName(e.target.value)} required />
                  </div>
                  <div className="form-group">
                    <label>Description</label>
                    <input type="text" className="form-input" value={newProdDesc} onChange={e => setNewProdDesc(e.target.value)} required />
                  </div>
                  <div className="form-group">
                    <label>Price ($)</label>
                    <input type="number" step="0.01" className="form-input" value={newProdPrice} onChange={e => setNewProdPrice(e.target.value)} required />
                  </div>
                  <div className="form-group">
                    <label>Category</label>
                    <select className="form-select" value={newProdCat} onChange={e => setNewProdCat(e.target.value)}>
                      <option value="Electronics">Electronics</option>
                      <option value="Furniture">Furniture</option>
                      <option value="Outdoor">Outdoor</option>
                      <option value="Apparel">Apparel</option>
                    </select>
                  </div>
                  
                  {/* Photo selector (Mock S3 upload) */}
                  <div className="form-group">
                    <label>Product Photo (Pushes to AWS S3)</label>
                    <input type="file" accept="image/*" onChange={handleProductImageUpload} className="form-input" style={{fontSize: '12px'}} />
                    {newProdImage && (
                      <div style={{marginTop: '10px'}}>
                        <div style={{fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px'}}>Image Preview:</div>
                        <img src={newProdImage} alt="Preview" style={{width: '90px', height: '60px', objectFit: 'cover', borderRadius: '8px', border: '1px solid var(--border-color)'}} />
                      </div>
                    )}
                  </div>

                  <div style={{display: 'flex', gap: '10px', marginTop: '10px'}}>
                    <button type="submit" className="btn-primary" style={{flex: 1}}>{editingProduct ? 'Save Changes' : 'Add Product'}</button>
                    {editingProduct && (
                      <button type="button" className="btn-secondary" onClick={cancelEditing}>Cancel</button>
                    )}
                  </div>
                </form>

                {/* Catalogue Items List & Stock Control Stacked */}
                <div style={{display: 'flex', flexDirection: 'column', gap: '24px', maxHeight: '580px', overflowY: 'auto'}}>
                  {/* Catalog Editing List */}
                  <div className="auth-box" style={{margin: '0', maxWidth: '100%', boxShadow: 'none', border: '1px solid var(--border-color)', background: '#f8fafc'}}>
                    <h3>Catalog Products</h3>
                    <div style={{marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '10px'}}>
                      {products.map(p => (
                        <div key={p.id} style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', background: '#ffffff', border: '1px solid var(--border-color)', borderRadius: '10px'}}>
                          <div style={{flex: 1, marginRight: '10px', display: 'flex', gap: '10px', alignItems: 'center'}}>
                            <img src={resolveProductImage(p.image_url, p.name)} alt="" style={{width: '36px', height: '36px', objectFit: 'cover', borderRadius: '6px'}} />
                            <div>
                              <div style={{fontWeight: '700', fontSize: '13px'}}>{p.name}</div>
                              <div style={{fontSize: '11px', color: 'var(--text-muted)'}}>{p.category} | ${p.price.toFixed(2)}</div>
                            </div>
                          </div>
                          <div style={{display: 'flex', gap: '6px'}}>
                            <button className="btn-secondary" onClick={() => startEditing(p)} style={{padding: '4px 8px', fontSize: '11px'}}>Edit</button>
                            <button className="btn-accent" onClick={() => handleDeleteProduct(p.id)} style={{padding: '4px 8px', fontSize: '11px'}}>Delete</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Stock Control */}
                  <div className="auth-box" style={{margin: '0', maxWidth: '100%', boxShadow: 'none', border: '1px solid var(--border-color)', background: '#f8fafc'}}>
                    <h3>Inventory stock counts</h3>
                    <div style={{marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '10px'}}>
                      {inventory.map(item => (
                        <div key={item.product_id} style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', background: '#ffffff', border: '1px solid var(--border-color)', borderRadius: '10px'}}>
                          <div>
                            <div style={{fontWeight: '700', fontSize: '13px'}}>{item.product_name}</div>
                            <div style={{fontSize: '11px', color: 'var(--text-muted)'}}>Reserved: {item.reserved_count}</div>
                          </div>
                          <div style={{display: 'flex', alignItems: 'center', gap: '10px'}}>
                            <span style={{fontWeight: '800', color: item.stock_count < 5 ? 'var(--accent)' : 'var(--secondary)'}}>{item.stock_count} units</span>
                            <button className="btn-secondary" onClick={() => handleUpdateStock(item.product_id, item.stock_count)} style={{padding: '4px 8px', fontSize: '11px'}}>Update</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}

          {activeTab === 'user' && (
            <>
              <div className="content-header">
                <div className="content-title">User Authentication Profile</div>
              </div>
              
              {!token ? (
                <div>
                  <div style={{display: 'flex', gap: '10px', justifyContent: 'center', marginBottom: '20px'}}>
                    <button className="btn-secondary" onClick={() => applyQuickAuth('Admin')}>Load Quick Admin</button>
                    <button className="btn-secondary" onClick={() => applyQuickAuth('Manager')}>Load Quick Manager</button>
                    <button className="btn-secondary" onClick={() => applyQuickAuth('Customer')}>Load Quick Customer</button>
                  </div>
                  
                  <form onSubmit={handleAuthSubmit} className="auth-box">
                    <h3>{isSignUp ? 'Create SmartRetailX Account' : 'Sign In'}</h3>
                    {authError && <div style={{color: 'var(--accent)', fontSize: '13px'}}>{authError}</div>}
                    
                    {isSignUp && (
                      <div className="form-group">
                        <label>Username</label>
                        <input type="text" className="form-input" value={authUsername} onChange={e => setAuthUsername(e.target.value)} required />
                      </div>
                    )}
                    
                    <div className="form-group">
                      <label>Email Address</label>
                      <input type="email" className="form-input" value={authEmail} onChange={e => setAuthEmail(e.target.value)} required />
                    </div>
                    
                    <div className="form-group">
                      <label>Password</label>
                      <input type="password" className="form-input" value={authPassword} onChange={e => setAuthPassword(e.target.value)} required />
                    </div>

                    {isSignUp && (
                      <div className="form-group">
                        <label>Assigned Role (RBAC Profile)</label>
                        <select className="form-select" value={authRole} onChange={e => setAuthRole(e.target.value)}>
                          <option value="Customer">Customer</option>
                          <option value="Manager">Manager</option>
                          <option value="Admin">Admin</option>
                        </select>
                      </div>
                    )}

                    <button type="submit" className="btn-primary">{isSignUp ? 'Sign Up' : 'Sign In'}</button>
                    
                    <span 
                      style={{fontSize: '13px', color: 'var(--primary)', textAlign: 'center', cursor: 'pointer', marginTop: '6px'}}
                      onClick={() => setIsSignUp(!isSignUp)}
                    >
                      {isSignUp ? 'Already have an account? Sign In' : 'Create new account'}
                    </span>
                  </form>
                </div>
              ) : (
                <div style={{display: 'grid', gridTemplateColumns: '320px 1fr', gap: '24px', alignItems: 'start'}}>
                  {/* Left card: Photo & Loyalty Summary */}
                  <div style={{display: 'flex', flexDirection: 'column', gap: '20px'}}>
                    <div className="auth-box" style={{margin: '0', maxWidth: '100%', alignItems: 'center', textAlign: 'center'}}>
                      {profilePic ? (
                        <img src={profilePic} alt="Profile" style={{width: '150px', height: '150px', borderRadius: '50%', objectFit: 'cover', border: '3px solid var(--primary)', boxShadow: 'var(--shadow-md)'}} />
                      ) : (
                        <div style={{width: '150px', height: '150px', borderRadius: '50%', backgroundColor: 'var(--primary-glow)', color: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '48px', fontWeight: '800', border: '3px solid rgba(255,80,0,0.2)'}}>
                          {user.username.substring(0,2).toUpperCase()}
                        </div>
                      )}

                      <h3 style={{marginTop: '12px'}}>{user.username}</h3>
                      <p style={{fontSize: '13px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: '700'}}>{user.role}</p>
                      
                      <label className="btn-secondary" style={{display: 'inline-block', cursor: 'pointer', marginTop: '16px', fontSize: '12px', padding: '8px 16px'}}>
                        Upload Profile Photo
                        <input type="file" accept="image/*" onChange={handleProfilePhotoUpload} style={{display: 'none'}} />
                      </label>
                    </div>

                    {/* Loyalty Points summary card */}
                    <div className="auth-box" style={{margin: '0', maxWidth: '100%', border: '1px solid var(--primary)', background: 'var(--primary-glow)', boxShadow: 'none'}}>
                      <h4 style={{color: 'var(--primary)', fontWeight: '700'}}>✨ Loyalty Points Balance</h4>
                      <div style={{fontSize: '36px', fontWeight: '900', color: 'var(--neutral-dark)', margin: '8px 0'}}>
                        {loyaltyPoints} <span style={{fontSize: '14px', fontWeight: '600', color: 'var(--text-secondary)'}}>points</span>
                      </div>
                      <p style={{fontSize: '11px', color: 'var(--text-secondary)', lineHeight: '1.4'}}>
                        Earned 1 point per $1 checked out! Next reward: <strong>500 points</strong> triggers a $15 discount voucher.
                      </p>
                    </div>

                    {/* Interactive Reward Vouchers Shop */}
                    <div className="auth-box" style={{margin: '0', maxWidth: '100%', border: '1px solid var(--border-color)', background: '#fff', boxShadow: 'none'}}>
                      <h4 style={{fontWeight: '700', marginBottom: '10px'}}>🎁 Loyalty Vouchers Shop</h4>
                      <div style={{display: 'flex', flexDirection: 'column', gap: '8px'}}>
                        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', padding: '8px 0', borderBottom: '1px solid var(--border-color)'}}>
                          <div>
                            <strong>Free Shipping</strong>
                            <div style={{fontSize: '10px', color: 'var(--text-muted)'}}>Cost: 100 points</div>
                          </div>
                          <button onClick={() => handleRedeemReward(100, 'FREE-SHIP-SRX')} className="btn-primary" style={{padding: '4px 8px', fontSize: '10px'}}>Redeem</button>
                        </div>
                        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', padding: '8px 0', borderBottom: '1px solid var(--border-color)'}}>
                          <div>
                            <strong>$5 Store Coupon</strong>
                            <div style={{fontSize: '10px', color: 'var(--text-muted)'}}>Cost: 200 points</div>
                          </div>
                          <button onClick={() => handleRedeemReward(200, 'SAVE-5-SRX')} className="btn-primary" style={{padding: '4px 8px', fontSize: '10px'}}>Redeem</button>
                        </div>
                        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', padding: '8px 0'}}>
                          <div>
                            <strong>$15 VIP Coupon</strong>
                            <div style={{fontSize: '10px', color: 'var(--text-muted)'}}>Cost: 400 points</div>
                          </div>
                          <button onClick={() => handleRedeemReward(400, 'VIP-15-SRX')} className="btn-primary" style={{padding: '4px 8px', fontSize: '10px'}}>Redeem</button>
                        </div>
                      </div>
                      {redeemedCoupon && (
                        <div style={{marginTop: '12px', padding: '8px', background: 'var(--neutral-light)', border: '1px dashed var(--primary)', borderRadius: '8px', fontSize: '11px', textAlign: 'center'}}>
                          Active Code: <strong>{redeemedCoupon}</strong>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Right card: Rich Account Details */}
                  <div className="auth-box" style={{margin: '0', maxWidth: '100%', display: 'flex', flexDirection: 'column', gap: '16px'}}>
                    <h3>Account Profile Details</h3>
                    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', fontSize: '13px', borderTop: '1px solid var(--border-color)', paddingTop: '16px'}}>
                      <div>
                        <strong style={{color: 'var(--text-secondary)'}}>Member ID:</strong>
                        <div style={{fontSize: '15px', fontWeight: '700', marginTop: '2px', color: 'var(--neutral-dark)'}}>#SRX-879430</div>
                      </div>
                      <div>
                        <strong style={{color: 'var(--text-secondary)'}}>Membership Tier:</strong>
                        <div style={{fontSize: '15px', fontWeight: '700', marginTop: '2px', color: 'var(--primary)'}}>SmartRetailX VIP Gold</div>
                      </div>
                      <div>
                        <strong style={{color: 'var(--text-secondary)'}}>Account Email:</strong>
                        <div style={{fontSize: '14px', marginTop: '2px', color: 'var(--neutral-dark)'}}>{user.email || `${user.username}@smartretailx.com`}</div>
                      </div>
                      <div>
                        <strong style={{color: 'var(--text-secondary)'}}>Registered On:</strong>
                        <div style={{fontSize: '14px', marginTop: '2px', color: 'var(--neutral-dark)'}}>{new Date().toLocaleDateString(undefined, {year: 'numeric', month: 'long', day: 'numeric'})}</div>
                      </div>
                    </div>

                    <div className="form-group" style={{marginTop: '12px'}}>
                      <label>Contact Number</label>
                      <input type="text" className="form-input" value={profilePhone} onChange={e => setProfilePhone(e.target.value)} />
                    </div>

                    <div className="form-group">
                      <label>Default Shipping Address</label>
                      <input type="text" className="form-input" value={profileAddress} onChange={e => setProfileAddress(e.target.value)} />
                    </div>

                    <div style={{display: 'flex', gap: '12px', marginTop: '12px'}}>
                      <button className="btn-primary" onClick={() => addLog("Profile settings updated.", "info")}>Save Changes</button>
                      <button className="btn-accent" onClick={handleLogout}>Log Out</button>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}

          {activeTab === 'observability' && isAuthorized && (
            <>
              <div className="content-header">
                <div className="content-title">System Metrics & Diagnostic Logs</div>
              </div>
              
              <div className="health-indicators">
                {Object.entries(serviceHealth).map(([service, status]) => (
                  <div className="health-card" key={service}>
                    <span className={`health-indicator-dot ${status ? 'active' : 'inactive'}`}></span>
                    {service.toUpperCase()}
                  </div>
                ))}
              </div>

              <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '24px'}}>
                <div className="auth-box" style={{margin: '0', maxWidth: '100%', boxShadow: 'none', border: '1px solid var(--border-color)', background: '#f8fafc'}}>
                  <h3>API Gateway Latency</h3>
                  <div style={{display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '12px'}}>
                    <div style={{display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid var(--border-color)'}}>
                      <span>Proxy Latency:</span>
                      <strong style={{color: 'var(--primary)'}}>{gatewayLatency.toFixed(1)} ms</strong>
                    </div>
                    <div style={{display: 'flex', justifyContent: 'space-between'}}>
                      <span>Route Mapping:</span>
                      <strong>FastAPI / httpx async</strong>
                    </div>
                  </div>
                </div>

                <div className="auth-box" style={{margin: '0', maxWidth: '100%', boxShadow: 'none', border: '1px solid var(--border-color)', background: '#f8fafc'}}>
                  <h3>MSK Kafka Broker Info</h3>
                  <div style={{display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '12px'}}>
                    <div style={{display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid var(--border-color)'}}>
                      <span>Partition Strategy:</span>
                      <strong>Topic-based Partitioning</strong>
                    </div>
                    <div style={{display: 'flex', justifyContent: 'space-between'}}>
                      <span>Local Broker Port:</span>
                      <strong>9092 (TCP)</strong>
                    </div>
                  </div>
                </div>
              </div>

              <div>
                <h3>Unified service logs</h3>
                <pre style={{whiteSpace: 'pre-wrap', background: '#0f172a', color: '#10b981', padding: '16px', borderRadius: '12px', fontSize: '12px', fontFamily: 'Courier New, monospace', maxHeight: '250px', overflowY: 'auto', marginTop: '10px'}}>
                  {logs.length === 0 ? "Listening for service logs..." : logs.join('\n')}
                </pre>
              </div>
            </>
          )}
        </main>
      </div>

      {/* ----------------------------------------------------
         Modal Screen: Beautiful Product Detail Pop-Up
         ---------------------------------------------------- */}
      {selectedProduct && (
        <div className="modal-overlay" onClick={() => setSelectedProduct(null)}>
          <div className="product-detail-modal" onClick={e => e.stopPropagation()}>
            <button className="modal-close-btn" onClick={() => setSelectedProduct(null)}>✕</button>
            <div className="modal-image-panel">
              <img src={resolveProductImage(selectedProduct.image_url, selectedProduct.name)} alt={selectedProduct.name} className="modal-image" />
              {selectedProduct.price > 100 && <span className="discount-tag">Summer Sale</span>}
            </div>
            <div className="modal-info-panel">
              <span className="store-card-category">{selectedProduct.category}</span>
              <h2 className="modal-title">{selectedProduct.name}</h2>
              
              <div className="rating-stars">
                <span>★</span><span>★</span><span>★</span><span>★</span><span>☆</span>
                <span style={{color: 'var(--text-muted)', fontSize: '12px', marginLeft: '6px'}}>(4.5 Rated Customer Choice)</span>
              </div>

              <p className="modal-desc">{selectedProduct.description || "Premium high-quality items designed for maximal efficiency and peak reliability. Sourced responsibly and delivered instantly via EKS automated orchestration."}</p>
              
              <div className="modal-price-row">
                <span style={{color: 'var(--text-secondary)', fontWeight: '600'}}>Price:</span>
                <span className="modal-price">${selectedProduct.price.toFixed(2)}</span>
              </div>

              <div style={{marginTop: '10px', display: 'flex', gap: '12px'}}>
                <button 
                  className="btn-primary" 
                  style={{flex: 1}} 
                  onClick={() => { addToCart(selectedProduct); setSelectedProduct(null); }}
                >
                  Add to Cart 🛒
                </button>
                <button className="btn-secondary" onClick={() => setSelectedProduct(null)}>Continue Shopping</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ----------------------------------------------------
         Modal Screen: Credit Card payment form details
         ---------------------------------------------------- */}
      {showPaymentForm && (
        <div className="modal-overlay" onClick={() => setShowPaymentForm(false)}>
          <div className="product-detail-modal" style={{maxWidth: '500px', padding: '24px'}} onClick={e => e.stopPropagation()}>
            <button className="modal-close-btn" onClick={() => setShowPaymentForm(false)}>✕</button>
            <h2 style={{marginBottom: '16px', textAlign: 'center'}}>Secure Checkout</h2>
            
            {/* Interactive Premium Virtual Credit Card */}
            <div className={`interactive-card-wrapper ${isCardFlipped ? 'flipped' : ''}`}>
              <div className="interactive-card-inner">
                {/* Front Side */}
                <div className="interactive-card-front">
                  <div className="card-top-row">
                    <div className="card-chip-icon"></div>
                    <div className="card-network-logo">
                      {cardNumber.startsWith('4') ? 'Visa' : cardNumber.startsWith('5') ? 'Mastercard' : 'Express'}
                    </div>
                  </div>
                  <div className="card-number-view">
                    {cardNumber || '•••• •••• •••• ••••'}
                  </div>
                  <div className="card-bottom-row">
                    <div className="card-holder-view">
                      <span>CARDHOLDER</span>
                      <div>{cardName.toUpperCase() || 'JOHN DOE'}</div>
                    </div>
                    <div className="card-expiry-view">
                      <span>EXPIRES</span>
                      <div>{cardExpiry || 'MM/YY'}</div>
                    </div>
                  </div>
                </div>

                {/* Back Side */}
                <div className="interactive-card-back">
                  <div className="card-mag-strip"></div>
                  <div className="card-sig-bar">
                    <div className="card-cvv-view">{cardCvv || '•••'}</div>
                  </div>
                  <div className="card-back-brand">SmartRetailX Secure</div>
                </div>
              </div>
            </div>

            {paymentErrors && (
              <div style={{backgroundColor: '#ffebe9', border: '1px solid var(--accent)', color: 'var(--accent)', padding: '10px', borderRadius: '8px', fontSize: '12px', marginBottom: '12px', fontWeight: '700'}}>
                ❌ {paymentErrors}
              </div>
            )}

            <form onSubmit={checkoutCart} style={{display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '20px'}}>
              <div className="form-group">
                <label>Cardholder Name</label>
                <input 
                  type="text" 
                  placeholder="John Doe" 
                  className="form-input" 
                  value={cardName} 
                  onChange={e => setCardName(e.target.value)} 
                  required 
                />
              </div>
              <div className="form-group">
                <label>Credit Card Number</label>
                <input 
                  type="text" 
                  placeholder="4111 2222 3333 4444" 
                  className="form-input" 
                  value={cardNumber} 
                  onChange={handleCardNumberChange} 
                  required 
                />
              </div>
              <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px'}}>
                <div className="form-group">
                  <label>Expiry Date</label>
                  <input 
                    type="text" 
                    placeholder="MM/YY" 
                    className="form-input" 
                    value={cardExpiry} 
                    onChange={handleExpiryChange} 
                    required 
                  />
                </div>
                <div className="form-group">
                  <label>Security Code (CVV)</label>
                  <input 
                    type="password" 
                    placeholder="***" 
                    className="form-input" 
                    value={cardCvv} 
                    onChange={handleCvvChange} 
                    onFocus={() => setIsCardFlipped(true)}
                    onBlur={() => setIsCardFlipped(false)}
                    required 
                  />
                </div>
              </div>
              <div style={{marginTop: '16px', display: 'flex', gap: '12px'}}>
                <button type="submit" className="btn-primary" style={{flex: 1}}>
                  Confirm Payment (${cart.reduce((sum, item) => sum + (item.quantity * item.price), 0).toFixed(2)})
                </button>
                <button type="button" className="btn-secondary" onClick={() => setShowPaymentForm(false)}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ----------------------------------------------------
         Modal Screen: Checkout / Payment Processing Screen
         ---------------------------------------------------- */}
      {checkoutState !== 'idle' && (
        <div className="modal-overlay">
          {checkoutState === 'processing' && (
            <div className="checkout-modal-panel">
              <h2>Securing Transaction</h2>
              <p style={{color: 'var(--text-secondary)'}}>Processing mock payment and committing ledger logs...</p>
              <div className="credit-card-loader">
                <div className="credit-card-chip"></div>
                <div className="credit-card-strip"></div>
              </div>
              <p style={{fontSize: '12px', color: 'var(--text-muted)'}}>Contacting PostgreSQL Payments Service...</p>
            </div>
          )}
          
          {checkoutState === 'success' && (
            <div className="checkout-modal-panel">
              <div className="success-checkmark">✓</div>
              <h2>Order Placed Successfully!</h2>
              <p style={{color: 'var(--text-secondary)'}}>Your checkout event has been pushed to Kafka.</p>
              
              {lastPlacedOrder && (
                <div style={{width: '100%', background: 'var(--neutral-light)', padding: '16px', borderRadius: '12px', margin: '12px 0', border: '1px solid var(--border-color)', textAlign: 'left', fontSize: '13px'}}>
                  <div style={{marginBottom: '6px'}}><strong>Order Reference:</strong> #{lastPlacedOrder.id.substring(lastPlacedOrder.id.length - 12)}</div>
                  <div style={{marginBottom: '6px'}}><strong>Total Paid:</strong> ${lastPlacedOrder.total_amount.toFixed(2)}</div>
                  <div><strong>Shipping to:</strong> {lastPlacedOrder.user_email}</div>
                </div>
              )}

              <button className="btn-primary" onClick={() => setCheckoutState('idle')} style={{width: '100%'}}>
                Back to Store
              </button>
            </div>
          )}
        </div>
      )}

      {/* ----------------------------------------------------
         AWS EKS Event Stream Broker Console
         Only visible when logged-in user is Admin or Manager
         ---------------------------------------------------- */}
      {isAuthorized && showDeveloperDock && (
        <div className="developer-dock">
          <div className="developer-dock-header">
            <span className="developer-dock-title">
              <span className="stream-pulse"></span>
              EKS Event stream (Kafka / MSK)
            </span>
            <button 
              onClick={() => setShowDeveloperDock(false)} 
              style={{background: 'none', border: 'none', color: 'white', cursor: 'pointer', fontWeight: '700'}}
            >
              ✕
            </button>
          </div>
          <div className="developer-stream">
            {notifications.length === 0 ? (
              <p style={{color: 'rgba(255,255,255,0.4)', fontSize: '11px', textAlign: 'center', marginTop: '30px'}}>
                No active events streamed yet. Place an order or modify inventory to test the MSK cluster queue.
              </p>
            ) : (
              notifications.map(n => (
                <div className={`developer-log-item ${n.type}`} key={n.id}>
                  <div style={{fontWeight: '700'}}>{n.title}</div>
                  <div>{n.message}</div>
                  <div className="developer-log-time">{n.timestamp}</div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Float button to restore Event Stream Dock (Only visible to Admin/Manager if closed) */}
      {isAuthorized && !showDeveloperDock && (
        <button 
          onClick={() => setShowDeveloperDock(true)}
          style={{position: 'fixed', right: '24px', bottom: '24px', backgroundColor: '#0f172a', color: '#38bdf8', border: '1px solid #38bdf8', padding: '10px 16px', borderRadius: '99px', fontSize: '12px', fontWeight: '700', cursor: 'pointer', zIndex: 1000, boxShadow: '0 4px 6px rgba(0,0,0,0.1)'}}
        >
          📂 Show Event Broker Stream
        </button>
      )}
    </div>
  );
}

export default App;
