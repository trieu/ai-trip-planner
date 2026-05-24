class TripPlannerApp {
  constructor() {
    this.baseUrl = "http://localhost:8888";
    this.currentLang = 'en';
    this.latestMarkdown = '';

    // i18n Dictionary
    this.translations = {
      en: {
        appTitle: "Trip Planner",
        heroTitle: "Plan Your Perfect Trip",
        heroSub: "Discover destinations, plan smarter budgets, and get a personalized day-by-day itinerary in seconds.",

        tagFast: "Plan faster",
        tagRoutes: "Smarter routes",
        tagGems: "Hidden gems",

        featResearch: "Research",
        featResearchSub: "Weather, highlights, and tips.",
        featItin: "Itineraries",
        featItinSub: "Smart day-by-day plans.",
        featBudget: "Budget",
        featBudgetSub: "Optimized spending.",
        featLocal: "Local",
        featLocalSub: "Authentic experiences.",

        formTitle: "Plan Your Trip",
        formSub: "Enter your destination, duration, budget, and interests.",

        lblDest: "Destination",
        lblDur: "Duration (days)",
        lblBudget: "Budget Style",
        lblInt: "Interests",

        optUltraBudget: "Ultra Budget (Bare minimum)",
        optBudget: "Budget (Save money)",
        optEconomy: "Economy (Low cost, good value)",
        optModerate: "Moderate (Balanced comfort)",
        optPremium: "Premium (High comfort)",
        optLuxury: "Luxury (Top-tier experience)",

        btnSubmit: "Plan My Trip",
        loading: "Planning your trip...",

        phTitle: "Start by filling out the form",
        phSub: "Your AI-generated itinerary will appear here.",

        resTitle: "Your Itinerary",
        btnCopy: "Copy",
        btnPrint: "Print",

        errGeneral: "Something went wrong while generating your plan. Please try again."
      },

      vi: {
        appTitle: "Lên Lịch Trình với AI",
        heroTitle: "Lên Kế Hoạch Chuyến Đi Hoàn Hảo",
        heroSub: "Khám phá điểm đến, tối ưu ngân sách và nhận lịch trình cá nhân hóa từng ngày chỉ trong vài giây.",

        tagFast: "Lên kế hoạch nhanh",
        tagRoutes: "Tối ưu lộ trình",
        tagGems: "Địa điểm độc đáo",

        featResearch: "Khám phá",
        featResearchSub: "Thời tiết, điểm nổi bật, mẹo hữu ích.",
        featItin: "Lịch trình",
        featItinSub: "Kế hoạch từng ngày thông minh.",
        featBudget: "Ngân sách",
        featBudgetSub: "Chi tiêu tối ưu.",
        featLocal: "Trải nghiệm",
        featLocalSub: "Đậm chất địa phương.",

        formTitle: "Lên Kế Hoạch Chuyến Đi",
        formSub: "Nhập điểm đến, số ngày, ngân sách và sở thích.",

        lblDest: "Điểm đến",
        lblDur: "Thời gian (ngày)",
        lblBudget: "Mức chi tiêu",
        lblInt: "Sở thích",

        optUltraBudget: "Siêu tiết kiệm (Chi tiêu tối thiểu)",
        optBudget: "Tiết kiệm (Giảm chi phí)",
        optEconomy: "Kinh tế (Chi phí thấp, hợp lý)",
        optModerate: "Vừa phải (Cân bằng tiện nghi)",
        optPremium: "Cao cấp (Thoải mái cao)",
        optLuxury: "Sang trọng (Trải nghiệm cao cấp)",

        btnSubmit: "Tạo Lịch Trình",
        loading: "Đang lên kế hoạch...",

        phTitle: "Bắt đầu bằng cách nhập thông tin",
        phSub: "Lịch trình do AI tạo sẽ hiển thị tại đây.",

        resTitle: "Lịch Trình Của Bạn",
        btnCopy: "Sao chép",
        btnPrint: "In",

        errGeneral: "Có lỗi xảy ra khi tạo lịch trình. Vui lòng thử lại."
      }
    };

    this.init();
  }

  init() {
    this.cacheDOM();
    this.bindEvents();
    lucide.createIcons();
  }

  cacheDOM() {
    this.$form = $('#plannerForm');
    this.$langSwitcher = $('#langSwitcher');
    this.$btnSubmit = $('#submitBtn');
    this.$btnText = this.$btnSubmit.find('.btn-text');
    this.$btnSpinner = this.$btnSubmit.find('.spinner-border');
    this.$placeholderCard = $('#placeholderCard');
    this.$resultsArea = $('#resultsArea');
    this.$itineraryContent = $('#itineraryContent');
    this.$copyBtn = $('#copyBtn');
    this.$printBtn = $('#printBtn');
  }

  bindEvents() {
    this.$langSwitcher.on('change', (e) => this.switchLanguage(e.target.value));
    this.$form.on('submit', (e) => this.handleSubmit(e));
    this.$printBtn.on('click', () => window.print());
    this.$copyBtn.on('click', () => this.copyToClipboard());
  }

  switchLanguage(lang) {
    this.currentLang = lang;
    const dict = this.translations[lang];

    $('[data-i18n]').each(function () {
      const key = $(this).data('i18n');
      if (dict[key]) $(this).text(dict[key]);
    });
  }

  setLoading(isLoading) {
    if (isLoading) {
      this.$btnSubmit.prop('disabled', true);
      this.$btnText.text(this.translations[this.currentLang].loading);
      this.$btnSpinner.removeClass('d-none');
      this.$placeholderCard.addClass('d-none');
      this.$resultsArea.removeClass('d-none');
      this.$itineraryContent.html(`
        <div class="d-flex justify-content-center py-5 text-secondary">
          <div class="spinner-border" role="status"></div>
        </div>
      `);
    } else {
      this.$btnSubmit.prop('disabled', false);
      this.$btnText.text(this.translations[this.currentLang].btnSubmit);
      this.$btnSpinner.addClass('d-none');
    }
  }

  async handleSubmit(e) {
    e.preventDefault();

    const payload = {
      destination: $('#destination').val().trim(),
      duration: `${$('#duration').val()} days`,
      budget: $('#budget').val(),
      interests: $('#interests').val().trim(),
      user_id: "demo_user_001",
      session_id: "web_debug_session"
    };

    this.setLoading(true);

    try {
      const response = await fetch(`${this.baseUrl}/travel/api/v1/trips/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await response.json();

      if (!response.ok) throw new Error(data?.detail || "HTTP Error");

      this.latestMarkdown = data.result || "No result generated.";
      this.renderMarkdown(this.latestMarkdown);

    } catch (error) {
      console.error("API Error:", error);
      this.showError(error.message);
    } finally {
      this.setLoading(false);
      lucide.createIcons();
    }
  }

  renderMarkdown(md) {
    const html = window.marked && window.marked.parse ? marked.parse(md) : `<pre>${md}</pre>`;
    this.$itineraryContent.html(html);
  }

  showError(msg) {
    this.$itineraryContent.html(`
      <div class="alert alert-danger d-flex align-items-center gap-2" role="alert">
        <i data-lucide="alert-triangle"></i>
        <div>${this.translations[this.currentLang].errGeneral}<br><small>${msg}</small></div>
      </div>
    `);
  }

  async copyToClipboard() {
    if (!this.latestMarkdown) return;
    try {
      await navigator.clipboard.writeText(this.latestMarkdown);
      const originalText = this.$copyBtn.html();
      this.$copyBtn.html('<i data-lucide="check" width="16"></i> Copied!');
      lucide.createIcons();
      setTimeout(() => {
        this.$copyBtn.html(originalText);
        lucide.createIcons();
      }, 2000);
    } catch (err) {
      console.error("Failed to copy", err);
    }
  }
}

// Initialize application when DOM is ready
$(document).ready(() => {
  window.app = new TripPlannerApp();
});
