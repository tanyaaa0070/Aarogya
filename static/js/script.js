let mediaRecorder;
let audioChunks = [];
let recordedBlob;

document.addEventListener('DOMContentLoaded', function() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    const recordBtn = document.getElementById('recordBtn');
    const imageFileInput = document.getElementById('image_file');
    const imagePreview = document.getElementById('imagePreview');
    const symptomForm = document.getElementById('symptomForm');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            const targetTab = this.dataset.tab;
            
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));
            
            this.classList.add('active');
            document.getElementById(targetTab).classList.add('active');
        });
    });
    
    if (recordBtn) {
        recordBtn.addEventListener('click', toggleRecording);
    }
    
    if (imageFileInput) {
        const uploadLabel = document.querySelector('.upload-label');
        if(uploadLabel) {
            uploadLabel.addEventListener('click', () => imageFileInput.click());
        }

        imageFileInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file && file.type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    imagePreview.innerHTML = `<img src="${e.target.result}" alt="Preview" style="max-width: 100%; border-radius: 0.5rem;">`;
                };
                reader.readAsDataURL(file);
            }
        });
    }
    
    if (symptomForm) {
        symptomForm.addEventListener('submit', handleFormSubmit);
    }
});

async function toggleRecording() {
    const recordBtn = document.getElementById('recordBtn');
    const recordingStatus = document.getElementById('recordingStatus');
    const audioPlayback = document.getElementById('audioPlayback');
    const submitBtn = document.querySelector('button[type="submit"]');

    if (!mediaRecorder || mediaRecorder.state === 'inactive') {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
            audioChunks = [];
            
            mediaRecorder.ondataavailable = (event) => {
                audioChunks.push(event.data);
            };
            
            mediaRecorder.onstop = () => {
                recordedBlob = new Blob(audioChunks, { type: 'audio/webm' });
                const audioUrl = URL.createObjectURL(recordedBlob);
                audioPlayback.src = audioUrl;
                audioPlayback.style.display = 'block';
                
                submitBtn.disabled = false;
                recordBtn.innerHTML = '<span id="recordIcon">🎤</span> Start Recording';
                recordingStatus.textContent = '✅ Recording saved. You can record again to overwrite.';
                recordBtn.style.background = '';
            };
            
            mediaRecorder.start();
            submitBtn.disabled = true; 
            recordBtn.innerHTML = '<span id="recordIcon">⏹️</span> Stop Recording';
            recordingStatus.textContent = '🔴 Recording...';
            recordBtn.style.background = 'var(--danger-color)';
        } catch (error) {
            alert('Error accessing microphone: ' + error.message);
            submitBtn.disabled = false;
        }
    } else {
        mediaRecorder.stop();
        mediaRecorder.stream.getTracks().forEach(track => track.stop());
    }
}

async function handleFormSubmit(e) {
    e.preventDefault();
    
    const progressModal = document.getElementById('progressModal');
    const progressText = document.getElementById('progressText');
    
    progressModal.classList.add('active');
    
    const formData = new FormData(e.target);
    
    if (recordedBlob) {
        formData.append('voice_file', recordedBlob, 'recording.webm');
    }

    const progressMessages = [
        'Analyzing symptoms...',
        'Processing recorded data...',
        'Running diagnostic simulation...',
        'Calculating triage level...',
        'Generating recommendations...'
    ];
    
    let messageIndex = 0;
    const messageInterval = setInterval(() => {
        progressText.textContent = progressMessages[messageIndex % progressMessages.length];
        messageIndex++;
    }, 800);
    
    try {
        const response = await fetch('/analyze', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        clearInterval(messageInterval);
        
        if (result.success) {
            progressText.textContent = 'Analysis complete! Redirecting...';
            setTimeout(() => {
                window.location.href = `/result?id=${result.record_id}`;
            }, 1000);
        } else {
            progressModal.classList.remove('active');
            alert('Error: ' + (result.error || 'Analysis failed'));
        }
    } catch (error) {
        clearInterval(messageInterval);
        progressModal.classList.remove('active');
        alert('Error submitting form: ' + error.message);
    }
}