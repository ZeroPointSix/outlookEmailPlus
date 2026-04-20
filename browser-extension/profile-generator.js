(function () {
  const SYMBOLS = '!@#$%^&*()-_=+';
  const LOWER = 'abcdefghijklmnopqrstuvwxyz';
  const UPPER = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  const DIGITS = '0123456789';

  function createRandom(seed) {
    let state = Number.isInteger(seed) ? seed >>> 0 : ((Date.now() ^ Math.floor(Math.random() * 0xffffffff)) >>> 0);
    const initialSeed = state;

    function next() {
      state += 0x6d2b79f5;
      let t = state;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    }

    return {
      initialSeed,
      next,
      int(min, max) {
        return Math.floor(next() * (max - min + 1)) + min;
      },
      pick(list) {
        return list[this.int(0, list.length - 1)];
      },
      shuffle(list) {
        const copy = list.slice();
        for (let index = copy.length - 1; index > 0; index -= 1) {
          const swapIndex = this.int(0, index);
          const temp = copy[index];
          copy[index] = copy[swapIndex];
          copy[swapIndex] = temp;
        }
        return copy;
      },
    };
  }

  function createId() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return `profile-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function normalizeWord(value) {
    return String(value || '')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '.')
      .replace(/^\.+|\.+$/g, '');
  }

  function generateUsername(firstName, lastName, random) {
    const first = normalizeWord(firstName);
    const last = normalizeWord(lastName);
    const templates = [
      `${first}.${last}`,
      `${first}${last}`,
      `${first}${last.charAt(0)}`,
      `${first.charAt(0)}${last}`,
      `${first}_${last}`,
    ];
    return `${random.pick(templates)}${random.int(11, 9999)}`;
  }

  function generateCompany(lastName, random, data) {
    const template = random.int(0, 2);
    if (template === 0) {
      return `${random.pick(data.companyPrefixes)} ${random.pick(data.companyNouns)}`;
    }
    if (template === 1) {
      return `${lastName} ${random.pick(data.companyNouns)}`;
    }
    return `${random.pick(data.companyPrefixes)} ${lastName} ${random.pick(['Co.', 'LLC', 'Inc.', 'Studio'])}`;
  }

  function generateAddress(random, data) {
    const state = random.pick(data.states);
    const city = random.pick(state.cities);
    const streetNumber = random.int(101, 9898);
    const streetName = random.pick(data.streetNames);
    const streetSuffix = random.pick(data.streetSuffixes);
    const postalCode = String(random.int(10000, 99999));
    const addressLine2 = random.next() > 0.72
      ? `${random.pick(data.unitPrefixes)} ${random.int(1, 999)}`
      : '';

    return {
      country: 'United States',
      countryCode: 'US',
      state: state.name,
      stateCode: state.code,
      city,
      postalCode,
      addressLine1: `${streetNumber} ${streetName} ${streetSuffix}`,
      addressLine2,
    };
  }

  function generatePhone(random, data) {
    const areaCode = random.pick(data.areaCodes);
    const prefix = random.int(200, 989);
    const line = random.int(1000, 9999);
    return `+1 (${areaCode}) ${prefix}-${line}`;
  }

  function generatePassword(length, seed) {
    const random = createRandom(seed);
    const size = clamp(Number(length) || 16, 8, 32);
    const buckets = [LOWER, UPPER, DIGITS, SYMBOLS];
    const chars = buckets.map((bucket) => bucket.charAt(random.int(0, bucket.length - 1)));
    const allChars = `${LOWER}${UPPER}${DIGITS}${SYMBOLS}`;

    while (chars.length < size) {
      chars.push(allChars.charAt(random.int(0, allChars.length - 1)));
    }

    return random.shuffle(chars).join('');
  }

  function buildEmail(firstName, lastName, random, data) {
    return `${generateUsername(firstName, lastName, random)}@${random.pick(data.emailDomains)}`;
  }

  function normalizeProfile(profile) {
    const next = Object.assign(
      {
        id: createId(),
        locale: 'en_US',
        country: 'United States',
        countryCode: 'US',
        firstName: '',
        lastName: '',
        fullName: '',
        username: '',
        password: '',
        email: '',
        phone: '',
        company: '',
        state: '',
        stateCode: '',
        city: '',
        postalCode: '',
        addressLine1: '',
        addressLine2: '',
        createdAt: new Date().toISOString(),
      },
      profile || {}
    );

    if (!next.fullName) {
      next.fullName = [next.firstName, next.lastName].filter(Boolean).join(' ').trim();
    }

    return next;
  }

  function createBlankProfile() {
    return normalizeProfile({
      password: generatePassword(16),
    });
  }

  function generateProfile(options) {
    const data = window.ProfileDataUS;
    const random = createRandom(options && options.seed);
    const firstName = random.pick(data.firstNames);
    const lastName = random.pick(data.lastNames);
    const address = generateAddress(random, data);
    const username = generateUsername(firstName, lastName, random);
    const company = generateCompany(lastName, random, data);

    return normalizeProfile({
      id: createId(),
      locale: 'en_US',
      seed: random.initialSeed,
      firstName,
      lastName,
      fullName: `${firstName} ${lastName}`,
      username,
      password: generatePassword(options && options.passwordLength, random.int(0, 0xffffffff)),
      email: options && options.claimedEmail ? options.claimedEmail : buildEmail(firstName, lastName, random, data),
      phone: generatePhone(random, data),
      company,
      state: address.state,
      stateCode: address.stateCode,
      city: address.city,
      postalCode: address.postalCode,
      country: address.country,
      countryCode: address.countryCode,
      addressLine1: address.addressLine1,
      addressLine2: address.addressLine2,
      createdAt: new Date().toISOString(),
    });
  }

  window.ProfileGenerator = {
    createBlankProfile,
    generatePassword,
    generateProfile,
    normalizeProfile,
  };
})();
