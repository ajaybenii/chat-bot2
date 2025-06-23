// State Management
const state = {
    step: 0,
    data: {
        userType: '',
        listingType: '',
        city: '',      // Stores cityName for UI
        cityId: '',    // NEW: Stores cityId for backend
        name: '',
        number: '',
        otp: '',
        user_id: ''
    },
    hasStarted: false,
    reminderTimeout: null,
    reminderShown: false,
    isOtpSent: false,
    otpAttempts: 0,
    maxOtpAttempts: 3,
    otpSentTime: null,
    otpValidDuration: 300000,
    resendCooldown: 30000,
    lastOtpSent: null,
    timerInterval: null,
    isLeadSubmitted: false,
    bypassOtp: false // For local testing
};

// Change cityList to store objects with name and id
let cityList = [];
let cityListFetched = false;
let popupInterval = null;
let currentAnimationStyle = 'bouncing-dots';
const animationStyles = ['bouncing-dots', 'horizontal-wave', 'rotating-squares'];
const popupMessages = [
    "List Your Property Fast!",
    "Sell or Rent in Minutes!",
    "Get Started with SquareYards!",
    "Post Your Listing Now!",
    "Find Buyers or Tenants Today!"
];


// DOM Elements
const chatbotIcon = document.querySelector('#chatbot-icon');
const chatbotPopup = document.querySelector('.chatbot-popup');
const chatbotWindow = document.querySelector('#chatbot-window');
const chatbotBodyDiv = document.querySelector('#chatbot-body');
const chatbotInputDiv = document.querySelector('#chatbot-input');
// const closeBtn = document.querySelector('.close-btn');
const themeToggleBtn = document.querySelector('.theme-toggle');
// const animationToggleBtn = document.querySelector('.animation-toggle');

// Utility Functions
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function showPopupMessage() {
    if (!chatbotIcon.classList.contains('closed')) {
        chatbotPopup.classList.remove('show');
        chatbotPopup.setAttribute('aria-hidden', 'true');
        return;
    }
    const randomMessage = popupMessages[Math.floor(Math.random() * popupMessages.length)];
    chatbotPopup.textContent = randomMessage;
    chatbotPopup.setAttribute('aria-label', randomMessage);
    chatbotPopup.setAttribute('aria-hidden', 'false');
    chatbotPopup.classList.add('show');
    setTimeout(() => {
        chatbotPopup.classList.remove('show');
        chatbotPopup.setAttribute('aria-hidden', 'true');
    }, 6000);
}

function startPopupInterval() {
    showPopupMessage();
    popupInterval = setInterval(showPopupMessage, 12000);
}

function stopPopupInterval() {
    clearInterval(popupInterval);
    chatbotPopup.classList.remove('show');
    chatbotPopup.setAttribute('aria-hidden', 'true');
}

// Event Listeners
themeToggleBtn.addEventListener('click', () => {
    const isDarkMode = chatbotWindow.classList.toggle('dark-mode');
    chatbotBodyDiv.classList.toggle('dark-mode');
    chatbotInputDiv.classList.toggle('dark-mode');
    themeToggleBtn.textContent = isDarkMode ? '☀️' : '🌙';
    document.querySelectorAll('.bot-message, .typing-indicator, .reminder-message, .final-message-container, .online-status, .online-dot, .input-wrapper input, .otp-input, .otp-timer').forEach(item => {
        item.classList.toggle('dark-mode', isDarkMode);
    });
});

// animationToggleBtn.addEventListener('click', () => {
//     const currentIndex = animationStyles.indexOf(currentAnimationStyle);
//     currentAnimationStyle = animationStyles[(currentIndex + 1) % animationStyles.length];
//     removeTypingIndicator();
//     showTypingIndicator();
//     setTimeout(removeTypingIndicator, 1000);
// });

chatbotIcon.addEventListener('click', () => toggleChatbot());
chatbotIcon.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggleChatbot();
    }
});

chatbotPopup.addEventListener('click', () => toggleChatbot());
chatbotPopup.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggleChatbot();
    }
});

// closeBtn.addEventListener('click', () => {
//     chatbotWindow.style.display = 'none';
//     chatbotWindow.classList.remove('open');
//     clearReminderTimeout();
//     clearInterval(state.timerInterval);
//     chatbotIcon.classList.remove('open');
//     chatbotIcon.classList.add('closed');
//     chatbotIcon.focus();
//     startPopupInterval();
// });

// API Functions
async function fetchCityList() {
    try {
        const response = await fetch('https://beats.squareyards.com/api/SecondaryPortal/getCityList', {
            method: 'POST',
            headers: {
                'api_key': 'uAqGJ6bvNqcqsxh4TXMRHP596adeEMLVomMZywp1U0VHUeHLwHxv5jbe5Aw8',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                fromSource: 'whatsapp',
                countryId: 1,
                userType: 'CP'
            })
        });
        const data = await response.json();
        console.log('City API Response:', data); // Debug
        if (data.status === 1 && data.mastercities && Array.isArray(data.mastercities)) {
            cityList = data.mastercities.map(city => ({
                name: city.cityName,
                id: city.cityid.toString()
            })).sort((a, b) => a.name.localeCompare(b.name));
            console.log('Available Cities:', cityList.map(c => ({ name: c.name, id: c.id }))); // Debug: Log city IDs
        } else {
            console.error('Failed to fetch city list:', data);
            addBotMessage('Error loading cities. Please try again.');
        }
    } catch (error) {
        console.error('Error fetching city list:', error);
        addBotMessage('Error loading cities. Please try again.');
    }
    cityListFetched = true;
}

async function sendOtp(number) {
    try {
        const response = await fetch('https://chat-bot2-backend.onrender.com/api/otp/send', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({
                countryCode: "91",
                mobile: number
            })
        });
        const result = await response.json();
        if (response.status === 200 && result.message === 'OTP sent Successfully on mobile') {
            state.otpSentTime = Date.now();
            state.lastOtpSent = Date.now();
            state.otpAttempts = 0;
            state.isOtpSent = true;
            return true;
        }
        return false;
    } catch (error) {
        console.error('Error sending OTP:', error);
        return false;
    }
}

async function verifyOtp(number, otp) {
    if (state.bypassOtp) return true; // Simulate OTP for testing
    try {
        const response = await fetch('https://chat-bot2-backend.onrender.com/api/otp/verify', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({
                countryCode: "91",
                mobile: number,
                otp: otp
            })
        });
        const result = await response.json();
        if (response.status === 200 && result.data && result.data.userExists) {
            return true;
        } else if (response.status === 400 && result.message === 'Invalid OTP') {
            return false;
        } else {
            throw new Error(result.message || 'Unknown error');
        }
    } catch (error) {
        console.error('Error verifying OTP:', error);
        return false;
    }
}

async function sendChatMessage(message) {
    try {
        const response = await fetch('https://chat-bot2-backend.onrender.com/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-User-Phone': state.data.user_id || 'anonymous'
            },
            body: JSON.stringify({
                message: message,
                city: state.data.city,
                user_id: state.data.user_id || 'anonymous'
            })
        });
        const result = await response.json();
        if (response.status === 200 && result.status === 'success') {
            return result.response;
        } else {
            throw new Error(result.detail || 'Failed to get response from chatbot.');
        }
    } catch (error) {
        console.error('Error sending chat message:', error);
        return 'Sorry, something went wrong. Please try again.';
    }
}

// OTP Timer
function startOtpTimer(resendButton, timerSpan) {
    let timeLeft = 30;
    timerSpan.textContent = `(Wait ${timeLeft}s)`;
    resendButton.disabled = true;
    resendButton.classList.remove('enabled');

    state.timerInterval = setInterval(() => {
        timeLeft--;
        timerSpan.textContent = `(Wait ${timeLeft}s)`;
        if (timeLeft <= 0) {
            clearInterval(state.timerInterval);
            resendButton.disabled = false;
            resendButton.classList.add('enabled');
            timerSpan.textContent = '';
        }
    }, 1000);
}

// Chatbot Logic
chatbotIcon.classList.add('closed');
startPopupInterval();

function toggleChatbot() {
    const isWindowOpen = chatbotWindow.classList.contains('open');
    if (isWindowOpen) {
        chatbotWindow.style.display = 'none';
        chatbotWindow.classList.remove('open');
        clearReminderTimeout();
        clearInterval(state.timerInterval);
        chatbotIcon.classList.remove('open');
        chatbotIcon.classList.add('closed');
        startPopupInterval();
    } else {
        chatbotWindow.style.display = 'block';
        chatbotWindow.classList.add('open');
        if (!state.hasStarted) {
            startChat();
            state.hasStarted = true;
        }
        chatbotIcon.classList.remove('closed');
        chatbotIcon.classList.add('open');
        stopPopupInterval();
        chatbotInputDiv.querySelector('input, button')?.focus();
    }
}

async function startChat() {
        addBotMessage('👋 Hi! Let’s list your property on SquareYards. 🚀');
        if (!cityListFetched) {
            fetchCityList().then(() => {
                cityListFetched = true;
            });
        }
        showStep(0);
    }



const steps = [
    {
        message: 'Are you the property owner or an agent? 🧑‍💼',
        input: 'buttons',
        options: ['Owner', 'Agent'],
        field: 'userType',
        reminder: '⏳ Are you still there? Please choose if you’re an owner or agent.'
    },
    {
        message: '🏠 Is the property for sale or rent? 💸',
        input: 'buttons',
        options: ['Sale', 'Rent'],
        field: 'listingType',
        reminder: '⏳ Are you still there? Please select if the property is for sale or rent.'
    },
    {
        message: '📍 Which city is your property in? 🌆 (Please select from the dropdown)',
        input: 'text',
        placeholder: 'Type and select a city (e.g., Mumbai)',
        field: 'city',
        validate: (value) => {
            if (value.trim().length === 0) {
                return 'Please enter a valid city.';
            }
            if (!cityList.some(city => city.name === value)) {
                return 'Please select a city from the dropdown list.';
            }
            return '';
        },
        reminder: '⏳ Are you still there? Please select your city from the dropdown.'
    },
    {
        message: '✨ To list your property quickly and hassle-free, our expert agent is ready to assist you personally! Please share your name. 📝',
        input: 'text',
        placeholder: 'Enter your full name',
        field: 'name',
        validate: (value) => {
            if (!/^[a-zA-Z\s]{1,20}$/.test(value)) {
                return 'Please enter a valid name (only letters, max 20 characters).';
            }
            return '';
        },
        reminder: '⏳ Are you still there? Please share your name.'
    },
    {
        message: '📞 Please enter your 10-digit phone number to receive an OTP for verification. 🔒 Your data is secure.',
        input: 'text',
        placeholder: 'Enter 10-digit phone number',
        field: 'number',
        validate: (value) => /^[0-9]{10}$/.test(value) ? '' : 'Please enter a valid 10-digit phone number.',
        reminder: '⏳ Are you still there? Please enter your phone number.'
    },
    {
            message: ' Please enter the 4-digit OTP sent to your phone number.',
            input: 'otp',
            placeholder: 'Enter OTP',
            field: 'otp',
            validate: (value) => /^[0-9]{4}$/.test(value) ? '' : 'Please enter a valid 4-digit OTP.',
            reminder: ' Are you still there? Please enter the OTP.'
        }


];

function showStep(stepIndex) {
    state.step = stepIndex;
    state.reminderTimeout = null;
    state.reminderShown = false;
    const step = steps[stepIndex];
    showTypingIndicator();
    setTimeout(() => {
        removeTypingIndicator();
        addBotMessage(step.message);
        setTimeout(() => {
            chatbotInputDiv.innerHTML = '';
            clearReminderTimeout();
            if (stepIndex !== 5) {
                state.reminderTimeout = setTimeout(() => {
                    if (!state.reminderShown) {
                        addBotMessage(step.reminder, 'reminder-message');
                        state.reminderShown = true;
                    }
                }, 20000); // Increased timeout for reminder
            }

            if (step.input === 'buttons') {
                const buttonsDiv = document.createElement('div');
                buttonsDiv.className = 'buttons';
                step.options.forEach((option, index) => {
                    const button = document.createElement('button');
                    button.textContent = option;
                    button.setAttribute('aria-label', `Select ${option}`);
                    button.addEventListener('click', () => handleButtonClick(option, step.field));
                    button.className = index === 0 ? 'default' : 'secondary';
                    buttonsDiv.appendChild(button);
                });
                chatbotInputDiv.appendChild(buttonsDiv);
                buttonsDiv.querySelector('button')?.focus();
            } else if (step.input === 'text') {
                const inputWrapper = document.createElement('div');
                inputWrapper.className = 'input-wrapper';

                const input = document.createElement('input');
                input.type = step.field === 'number' ? 'tel' : 'text';
                input.placeholder = step.placeholder;
                input.setAttribute('aria-label', step.placeholder);
                input.classList.toggle('dark-mode', chatbotWindow.classList.contains('dark-mode'));
                if (step.field === 'number') {
                    input.pattern = '[0-9]{10}';
                    input.maxLength = 10;
                } else if (step.field === 'name') {
                    input.maxLength = 20;
                    input.addEventListener('input', () => {
                        input.value = input.value.replace(/[^a-zA-Z\s]/g, '');
                    });
                }

                const submitArrow = document.createElement('span');
                submitArrow.className = 'submit-arrow';
                submitArrow.innerHTML = '➔';
                submitArrow.setAttribute('aria-label', 'Submit input');

                inputWrapper.appendChild(input);
                inputWrapper.appendChild(submitArrow);

                chatbotInputDiv.appendChild(inputWrapper);

                const errorDiv = document.createElement('div');
                errorDiv.className = 'error-message';
                chatbotInputDiv.appendChild(errorDiv);

                if (step.field === 'city') {
                    const dropdown = document.createElement('div');
                    dropdown.className = 'autocomplete-dropdown';
                    inputWrapper.appendChild(dropdown);

                    let activeIndex = -1;

                    const debouncedAutocomplete = debounce((value, dropdown) => {
                        dropdown.innerHTML = '';
                        activeIndex = -1;

                        if (value.trim().length === 0) {
                            dropdown.style.display = 'none';
                            dropdown.classList.remove('active');
                            return;
                        }

                        const filteredCities = cityList.filter(city =>
                            city.name.toLowerCase().startsWith(value.toLowerCase())
                        );

                        if (filteredCities.length > 0) {
                            filteredCities.slice(0, 5).forEach((city, index) => {
                                const item = document.createElement('div');
                                item.className = 'autocomplete-item';
                                item.textContent = city.name; // Show cityName
                                item.setAttribute('tabindex', '0');
                                item.setAttribute('role', 'option');
                                item.addEventListener('click', () => {
                                    input.value = city.name;
                                    state.data.cityId = city.id; // Store cityId
                                    dropdown.innerHTML = '';
                                    dropdown.style.display = 'none';
                                    dropdown.classList.remove('active');
                                    handleTextInput(city.name, step.field, step.validate, errorDiv);
                                });
                                item.addEventListener('keydown', (e) => {
                                    if (e.key === 'Enter') {
                                        input.value = city.name;
                                        state.data.cityId = city.id; // Store cityId
                                        dropdown.innerHTML = '';
                                        dropdown.style.display = 'none';
                                        dropdown.classList.remove('active');
                                        handleTextInput(city.name, step.field, step.validate, errorDiv);
                                    }
                                });
                                dropdown.appendChild(item);
                            });
                            dropdown.style.display = 'block';
                            dropdown.classList.add('active');
                        } else {
                            dropdown.style.display = 'none';
                            dropdown.classList.remove('active');
                        }
                    }, 300);

                    input.addEventListener('input', (e) => {
                        console.log('City input:', e.target.value); // Debug
                        debouncedAutocomplete(e.target.value, dropdown);
                        if (step.validate) {
                            errorDiv.textContent = step.validate(e.target.value);
                        }
                    });

                    input.addEventListener('keydown', (e) => {
                        const items = dropdown.querySelectorAll('.autocomplete-item');
                        if (items.length === 0) return;

                        if (e.key === 'ArrowDown') {
                            e.preventDefault();
                            activeIndex = (activeIndex + 1) % items.length;
                            updateActiveItem(activeIndex, items);
                            items[activeIndex].focus();
                        } else if (e.key === 'ArrowUp') {
                            e.preventDefault();
                            activeIndex = (activeIndex - 1 + items.length) % items.length;
                            updateActiveItem(activeIndex, items);
                            items[activeIndex].focus();
                        } else if (e.key === 'Enter' && activeIndex >= 0) {
                            e.preventDefault();
                            const selectedCity = filteredCities[activeIndex];
                            input.value = selectedCity.name;
                            state.data.cityId = selectedCity.id; // Store cityId
                            dropdown.innerHTML = '';
                            dropdown.style.display = 'none';
                            dropdown.classList.remove('active');
                            handleTextInput(selectedCity.name, step.field, step.validate, errorDiv);
                        } else if (e.key === 'Enter') {
                            e.preventDefault();
                            const selectedCity = cityList.find(city => city.name === input.value);
                            if (selectedCity) {
                                state.data.cityId = selectedCity.id; // Store cityId
                                dropdown.innerHTML = '';
                                dropdown.style.display = 'none';
                                dropdown.classList.remove('active');
                                handleTextInput(input.value, step.field, step.validate, errorDiv);
                            } else {
                                errorDiv.textContent = 'Please select a city from the dropdown list.';
                            }
                        } else if (e.key === 'Escape') {
                            dropdown.innerHTML = '';
                            dropdown.style.display = 'none';
                            dropdown.classList.remove('active');
                        }
                    });

                    submitArrow.addEventListener('click', () => {
                        const selectedCity = cityList.find(city => city.name === input.value);
                        if (selectedCity) {
                            state.data.cityId = selectedCity.id; // Store cityId
                            dropdown.innerHTML = '';
                            dropdown.style.display = 'none';
                            dropdown.classList.remove('active');
                            handleTextInput(input.value, step.field, step.validate, errorDiv);
                        } else {
                            errorDiv.textContent = 'Please select a city from the dropdown list.';
                        }
                    });

                    document.addEventListener('click', (e) => {
                        if (!inputWrapper.contains(e.target)) {
                            dropdown.innerHTML = '';
                            dropdown.style.display = 'none';
                            dropdown.classList.remove('active');
                        }
                    });

                    function updateActiveItem(index, items) {
                        items.forEach(item => item.classList.remove('active'));
                        items[index].classList.add('active');
                        items[index].scrollIntoView({ block: 'nearest' });
                    }
                } else {
                    input.addEventListener('input', () => {
                        if (step.validate) {
                            errorDiv.textContent = step.validate(input.value);
                        }
                    });
                    input.addEventListener('keypress', (e) => {
                        if (e.key === 'Enter') {
                            handleTextInput(input.value, step.field, step.validate, errorDiv);
                        }
                    });
                    submitArrow.addEventListener('click', () => {
                        handleTextInput(input.value, step.field, step.validate, errorDiv);
                    });
                }

                input.focus();
            } else if (step.input === 'otp') {
                const otpContainer = document.createElement('div');
                otpContainer.className = 'otp-container';

                const inputs = [];
                for (let i = 0; i < 4; i++) {
                    const input = document.createElement('input');
                    input.type = 'text';
                    input.className = 'otp-input';
                    input.maxLength = 1;
                    input.pattern = '[0-9]';
                    input.inputMode = 'numeric';
                    input.setAttribute('aria-label', `OTP digit ${i + 1}`);
                    input.classList.toggle('dark-mode', chatbotWindow.classList.contains('dark-mode'));
                    input.addEventListener('input', (e) => {
                        e.target.value = e.target.value.replace(/[^0-9]/g, '');
                        if (e.target.value.length === 1 && i < 3) {
                            inputs[i + 1].focus();
                        }
                        const otp = inputs.map(inp => inp.value).join('');
                        if (otp.length === 4) {
                            clearInterval(state.timerInterval);
                            timerSpan.textContent = '';
                            handleTextInput(otp, step.field, step.validate, errorDiv);
                        }
                    });
                    input.addEventListener('keydown', (e) => {
                        if (e.key === 'Backspace' && input.value === '' && i > 0) {
                            inputs[i - 1].focus();
                        }
                    });
                    otpContainer.appendChild(input);
                    inputs.push(input);
                }

                const errorDiv = document.createElement('div');
                errorDiv.className = 'error-message';
                chatbotInputDiv.appendChild(otpContainer);
                chatbotInputDiv.appendChild(errorDiv);

                const resendDiv = document.createElement('div');
                resendDiv.className = 'otp-resend';
                const resendButton = document.createElement('button');
                resendButton.textContent = 'Resend OTP';
                const timerSpan = document.createElement('span');
                timerSpan.className = 'otp-timer';
                timerSpan.classList.toggle('dark-mode', chatbotWindow.classList.contains('dark-mode'));
                resendDiv.appendChild(timerSpan);
                resendDiv.appendChild(resendButton);

                const editNumberButton = document.createElement('button');
                editNumberButton.textContent = 'Edit Number';
                editNumberButton.setAttribute('aria-label', 'Edit phone number');
                editNumberButton.className = 'secondary';
                editNumberButton.addEventListener('click', () => {
                    const chatSound = document.getElementById('chatSound');
                    if (chatSound) {
                        chatSound.currentTime = 0;
                        chatSound.play().catch(error => console.error('Chat sound error:', error));
                    }
                    state.data.number = '';
                    state.data.otp = '';
                    state.isOtpSent = false;
                    state.otpAttempts = 0;
                    state.otpSentTime = null;
                    state.lastOtpSent = null;
                    clearInterval(state.timerInterval);
                    clearReminderTimeout();
                    addBotMessage('Please enter your correct phone number.');
                    showStep(4);
                });
                resendDiv.appendChild(editNumberButton);

                chatbotInputDiv.appendChild(resendDiv);

                startOtpTimer(resendButton, timerSpan);

                resendButton.addEventListener('click', async () => {
                    if (resendButton.disabled) {
                        errorDiv.textContent = 'Please wait before resending OTP.';
                        return;
                    }
                    showTypingIndicator();
                    const success = await sendOtp(state.data.number);
                    removeTypingIndicator();
                    if (success) {
                        addBotMessage('OTP resent successfully.');
                        startOtpTimer(resendButton, timerSpan);
                    } else {
                        errorDiv.textContent = 'Failed to resend OTP. Please try again.';
                    }
                });

                inputs[0].focus();
            }
        }, 300);
    }, 800);
}

function clearReminderTimeout() {
    if (state.reminderTimeout) {
        clearTimeout(state.reminderTimeout);
        state.reminderTimeout = null;
    }
}

function showTypingIndicator() {
    const indicator = document.createElement('div');
    indicator.className = `message typing-indicator ${currentAnimationStyle}`;
    indicator.setAttribute('aria-hidden', 'true');
    indicator.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
    if (chatbotWindow.classList.contains('dark-mode')) {
        indicator.classList.add('dark-mode');
    }
    chatbotBodyDiv.appendChild(indicator);
    chatbotBodyDiv.scrollTop = chatbotBodyDiv.scrollHeight;
}

function removeTypingIndicator() {
    const indicator = chatbotBodyDiv.querySelector('.typing-indicator');
    if (indicator) {
        indicator.remove();
    }
}

function addBotMessage(htmlContent, className = 'bot-message', timeout = 0) {
    const message = document.createElement('div');
    message.className = `message ${className}`;
    if (chatbotWindow.classList.contains('dark-mode')) {
        message.classList.add('dark-mode');
    }
    message.innerHTML = htmlContent;
    chatbotBodyDiv.appendChild(message);

    if (timeout > 0) {
        setTimeout(() => message.remove(), timeout);
    }

    const isScrolledToBottom = chatbotBodyDiv.scrollHeight - chatbotBodyDiv.scrollTop - chatbotBodyDiv.clientHeight < 600;
    if (isScrolledToBottom) {
        chatbotBodyDiv.scrollTo({
            top: chatbotBodyDiv.scrollHeight,
            behavior: 'smooth'
        });
    }
}

function addUserMessage(text, isSelectedOption = false) {
    const message = document.createElement('div');
    message.className = 'message user-message';
    if (isSelectedOption) {
        message.classList.add('selected-option');
    }
    message.textContent = text;
    chatbotBodyDiv.appendChild(message);

    const isScrolledToBottom = chatbotBodyDiv.scrollHeight - chatbotBodyDiv.scrollTop - chatbotBodyDiv.clientHeight < 600;
    if (isScrolledToBottom) {
        chatbotBodyDiv.scrollTo({
            top: chatbotBodyDiv.scrollHeight,
            behavior: 'smooth'
        });
    }
}

async function handleButtonClick(value, field) {
    clearReminderTimeout();
    state.data[field] = value;
    addUserMessage(value, true);
    const chatSound = document.getElementById('chatSound');
    if (chatSound) {
        chatSound.currentTime = 0;
        chatSound.play().catch(error => console.error('Chat sound error:', error));
    }
    proceedToNextStep();
}

async function handleTextInput(value, field, validate, errorDiv) {
    const error = validate ? validate(value) : '';
    if (error) {
        errorDiv.textContent = error;
        const errorSound = document.getElementById('errorSound');
        if (errorSound) {
            errorSound.currentTime = 0;
            errorSound.play().catch(error => console.error('Error sound error:', error));
        }
        return;
    }
    clearReminderTimeout();
    state.data[field] = value;

    if (field === 'otp' && !state.bypassOtp) {
        if (state.otpAttempts >= state.maxOtpAttempts) {
            errorDiv.textContent = 'Maximum OTP attempts reached. Please resend OTP.';
            return;
        }
        if (Date.now() - state.otpSentTime > state.otpValidDuration) {
            errorDiv.textContent = 'OTP has expired. Please resend OTP.';
            return;
        }
        state.otpAttempts++;
        showTypingIndicator();
        const success = await verifyOtp(state.data.number, value);
        removeTypingIndicator();
        if (!success) {
            errorDiv.textContent = `Invalid OTP. ${state.maxOtpAttempts - state.otpAttempts} attempts remaining.`;
            return;
        }
        addUserMessage('****');
    } else if (field === 'otp' && state.bypassOtp) {
        // addUserMessage('****');
    } else {
        addUserMessage(value);
    }

    if (field === 'number' && !state.bypassOtp) {
        showTypingIndicator();
        const success = await sendOtp(value);
        removeTypingIndicator();
        if (!success) {
            errorDiv.textContent = 'Failed to send OTP. Please try again.';
            return;
        }
        addBotMessage('OTP sent successfully to your phone number.');
        state.isOtpSent = true;
    } else if (field === 'number' && state.bypassOtp) {
        state.isOtpSent = true;
        state.data.user_id = value;
    }

    if (field === 'number') {
        state.data.user_id = value;
    }

    if (field === 'name' || field === 'number' || field === 'city') {
        const chatSound = document.getElementById('chatSound');
        if (chatSound) {
            chatSound.currentTime = 0;
            chatSound.play().catch(error => console.error('Chat sound error:', error));
        }
    }

    proceedToNextStep();
}

function proceedToNextStep() {
    if (state.step < steps.length - 1) {
        if (state.bypassOtp && state.step === 4) {
            state.data.otp = '1234';
            state.isOtpSent = true;
            state.otpAttempts = 0;
            clearReminderTimeout();
            clearInterval(state.timerInterval);
            addUserMessage('****');
            submitToBackend();
        } else {
            setTimeout(() => showStep(state.step + 1), 500);
        }
    } else {
        clearReminderTimeout();
        clearInterval(state.timerInterval);
        submitToBackend();
    }
}

function showFinalButtons() {
    chatbotInputDiv.innerHTML = '';
    const buttonsDiv = document.createElement('div');
    buttonsDiv.className = 'buttons';

    const startNewBtn = document.createElement('button');
    startNewBtn.textContent = 'Start New Listing';
    startNewBtn.className = 'default';
    startNewBtn.setAttribute('aria-label', 'Start new listing');
    startNewBtn.addEventListener('click', clearChat);
    buttonsDiv.appendChild(startNewBtn);

    chatbotInputDiv.appendChild(buttonsDiv);
    buttonsDiv.querySelector('button')?.focus();
}

function showChatInput() {
    chatbotInputDiv.innerHTML = '';

    const inputWrapper = document.createElement('div');
    inputWrapper.className = 'input-wrapper';

    const input = document.createElement('input');
    input.type = 'text';
    input.placeholder = 'Ask about properties...';
    input.setAttribute('aria-label', 'Ask about properties');
    input.classList.toggle('dark-mode', chatbotWindow.classList.contains('dark-mode'));

    const submitArrow = document.createElement('span');
    submitArrow.className = 'submit-arrow';
    submitArrow.innerHTML = '➔';
    submitArrow.setAttribute('aria-label', 'Send message');

    inputWrapper.appendChild(input);
    inputWrapper.appendChild(submitArrow);

    chatbotInputDiv.appendChild(inputWrapper);

    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message';
    chatbotInputDiv.appendChild(errorDiv);

    input.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter' && input.value.trim()) {
            const message = input.value.trim();
            addUserMessage(message);
            input.value = '';
            showTypingIndicator();
            const response = await sendChatMessage(message);
            removeTypingIndicator();
            addBotMessage(response);
        }
    });

    submitArrow.addEventListener('click', async () => {
        if (input.value.trim()) {
            const message = input.value.trim();
            addUserMessage(message);
            input.value = '';
            showTypingIndicator();
            const response = await sendChatMessage(message);
            removeTypingIndicator();
            addBotMessage(response);
        } 
    });

    const buttonsDiv = document.createElement('div');
    buttonsDiv.className = 'buttons';

    const startNewBtn = document.createElement('button');
    startNewBtn.textContent = 'Start New Listing';
    startNewBtn.className = 'default';
    startNewBtn.setAttribute('aria-label', 'Start new listing');
    startNewBtn.addEventListener('click', clearChat);
    buttonsDiv.appendChild(startNewBtn);

    chatbotInputDiv.appendChild(buttonsDiv);

    input.focus();
}

async function submitToBackend() {
    try {
        const payload = {
            customerName: state.data.name,
            customerEmail: "",
            customerPhoneNumber: `91-${state.data.number}`,
            source: "WhatsAppChat",
            countryId: 1,
            requirementType: 0,
            listingType: state.data.listingType === "Sale" ? "1" : "2",
            cityId: state.data.cityId,
            userType: state.data.userType.toUpperCase()
        };

        // Log request body prominently
        console.log('===== REQUEST BODY SENT TO API =====');
        console.log(JSON.stringify(payload, null, 2));
        console.log('===================================');
        console.log('State data:', state.data);

        // Validate payload
        if (!state.data.cityId || !cityList.some(city => city.id === state.data.cityId)) {
            console.error('Invalid cityId:', state.data.cityId);
            addBotMessage('Error: Invalid city selected. Please choose a valid city.');
            showRestartButton();
            return;
        }

        if (!/^91-[6-9][0-9]{9}$/.test(payload.customerPhoneNumber)) {
            console.error('Invalid phone number:', payload.customerPhoneNumber);
            addBotMessage('Error: Please enter a valid Indian phone number (10 digits, starting with 6-9).');
            showRestartButton();
            return;
        }

        // Log request headers
        const headers = {
            'Content-Type': 'application/json',
            'api_key': 'uAqGJ6bvNqcqsxh4TXMRHP596adeEMLVomMZywp1U0VHUeHLwHxv5jbe5Aw8=',
            'User-Agent': 'curl/7.68.0' // Mimic cURL
        };
        console.log('===== REQUEST HEADERS =====');
        console.log(headers);
        console.log('===========================');

        const response = await fetch('https://beatsdemo.squareyards.com/api/SecondaryPortal/ownerRegistration', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(payload),
            mode: 'cors',
            credentials: 'omit'
        });

        console.log('API Response Status:', response.status);
        console.log('API Response Headers:', Object.fromEntries(response.headers));

        let result;
        try {
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                result = await response.json();
                console.log('API Response JSON:', result);
            } else {
                result = await response.text();
                console.log('API Response Text:', result);
            }
        } catch (jsonError) {
            console.error('JSON Parse Error:', jsonError.message);
            result = await response.text();
            console.log('API Response Text (after JSON error):', result);
        }

        if (response.status === 200 && typeof result === 'object' && result.status === 1) {
            state.isLeadSubmitted = true;
            showTypingIndicator();
            setTimeout(() => {
                removeTypingIndicator();
                addBotMessage(`Thank you, ${state.data.name}! Your phone number has been verified. Our agent will contact you soon to list your property in ${state.data.city}. 🙌`);
                addBotMessage(`
                    <div class="online-status">
                        <span class="online-dot"></span>
                        <span>Agent Online</span>
                    </div>
                    <div class="final-message-container">
                        <img src="assets/images/bot-icon-white.svg" alt="Agent" class="agent-image">
                        <div class="final-message-text">
                            📞 Our expert will call you soon to list your property in ${state.data.city} 🏠 – get started with SquareYards today! 🚀
                        </div>
                    </div>
                `);
                addBotMessage('Feel free to ask any questions about properties or real estate 🏠 in your city!');
                setTimeout(() => {
                    showChatInput();
                    chatbotInputDiv.querySelector('input')?.focus();
                }, 300);
            }, 800);
        } else if (response.status === 403) {
            console.error('Forbidden error:', result);
            let errorMessage = '';
            if (typeof result === 'object' && result.message) {
                errorMessage += ` ${result.message}`;
            } else if (result.includes('duplicate')) {
                errorMessage += ' Phone number already registered. Please use a different number.';
            } else {
                errorMessage += ' Please try a different phone number or contact support.';
            }
            addBotMessage(errorMessage);
            showRestartButton();
        } else if (response.status === 401) {
            console.error('Unauthorized error:', result);
            addBotMessage('Error: Invalid API key. Please contact support.');
            showRestartButton();
        } else {
            console.error('Submission failed:', { status: response.status, result });
            addBotMessage(`Error: Failed to save data (Status: ${response.status}). ${typeof result === 'string' ? result : result.message || 'Please try again.'}`);
            showRestartButton();
        }
    } catch (error) {
        console.error('Fetch error:', error.message);
        let errorMessage = 'Error: Unable to connect to the server.';
        if (error.message.includes('CORS')) {
            errorMessage += ' CORS issue detected. Please contact support.';
        } else {
            errorMessage += ` ${error.message || 'Please try again later.'}`;
        }
        addBotMessage(errorMessage);
        showRestartButton();
    }
}

function showRestartButton() {
    chatbotInputDiv.innerHTML = '';
    const buttonsDiv = document.createElement('div');
    buttonsDiv.className = 'buttons';
    const restartBtn = document.createElement('button');
    restartBtn.textContent = 'Restart Listing';
    restartBtn.className = 'default';
    restartBtn.setAttribute('aria-label', 'Restart listing');
    restartBtn.addEventListener('click', clearChat);
    buttonsDiv.appendChild(restartBtn);
    chatbotInputDiv.appendChild(buttonsDiv);
    restartBtn.focus();
}

function clearChat() {
    state.step = 0;
    state.data = {
        userType: '',
        listingType: '',
        city: '',
        name: '',
        number: '',
        otp: '',
        user_id: ''
    };
    state.hasStarted = false;
    state.reminderTimeout = null;
    state.reminderShown = false;
    state.isOtpSent = false;
    state.otpAttempts = 0;
    state.otpSentTime = null;
    state.lastOtpSent = null;
    state.isLeadSubmitted = false;
    clearReminderTimeout();
    clearInterval(state.timerInterval);
    chatbotBodyDiv.innerHTML = '';
    chatbotInputDiv.innerHTML = '';
    startChat();
}