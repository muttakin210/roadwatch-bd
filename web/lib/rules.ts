// Bangladesh traffic rules and maximum penalties, from the Road Transport Act 2018 (সড়ক পরিবহণ আইন, ২০১৮,
// Act No. 47 of 2018), consolidated text on http://bdlaws.minlaw.gov.bd/act-details-1262.html, checked 2026-11-05.
// `rule` = the section that states the duty, `penalty` = the section that punishes breaking it.
// Amounts are the legal MAXIMUM (a court or mobile court decides the actual fine). Keep this file in step with the act.

export type Cat = "everyone" | "pedestrian" | "car" | "motorcycle" | "bus" | "truck" | "cng" | "papers";
/** "driver" = every motor-vehicle driver (car, motorcycle, bus, truck, CNG, ...) */
type For = Cat | "driver";

export type Penalty = {
  jailMonths?: { min?: number; max: number };
  fineBdt?: { min?: number; max: number };
  /** demerit points cut from the 12 on a driving licence (s.11), drivers only */
  points?: number;
  /** "or" (either/both) is the act's usual wording; "fine" = fine only */
  note?: { en: string; bn: string };
};

export type Rule = {
  id: string;
  for: For[];
  title: { en: string; bn: string };
  detail: { en: string; bn: string };
  rule: string;
  penalty: string;
  p: Penalty;
  /** RoadWatch's AI can flag this in a video */
  detects?: boolean;
};

const D: For[] = ["driver"];

export const RULES: Rule[] = [
  // ------------------------------------------------------------------ licence & papers
  {
    id: "licence", for: ["driver", "papers"],
    title: { en: "Drive only with a valid driving licence", bn: "বৈধ ড্রাইভিং লাইসেন্স ছাড়া গাড়ি চালানো যাবে না" },
    detail: {
      en: "No driving (or letting someone drive) in a public place without a licence or learner licence, with an expired one, or in a vehicle class the licence doesn't cover. Minimum age: 18 for a non-professional and 21 for a professional licence (s.6).",
      bn: "লাইসেন্স বা শিক্ষানবিশ লাইসেন্স ছাড়া, মেয়াদোত্তীর্ণ লাইসেন্সে, অথবা লাইসেন্সের শ্রেণির বাইরের গাড়ি পাবলিক প্লেসে চালানো বা চালাতে দেওয়া যাবে না। বয়স: অপেশাদার লাইসেন্সে কমপক্ষে ১৮, পেশাদারে ২১ বছর (ধারা ৬)।",
    },
    rule: "4", penalty: "66", p: { jailMonths: { max: 6 }, fineBdt: { max: 25_000 } },
  },
  {
    id: "public-permit", for: ["bus", "papers"],
    title: { en: "Public transport needs a driving permit", bn: "গণপরিবহণ চালাতে অনুমতিপত্র লাগবে" },
    detail: {
      en: "Driving public transport needs a permit from BRTA, on top of the licence.",
      bn: "লাইসেন্সের পাশাপাশি গণপরিবহণ চালাতে কর্তৃপক্ষের (বিআরটিএ) অনুমতিপত্র লাগবে।",
    },
    rule: "5", penalty: "66", p: { jailMonths: { max: 6 }, fineBdt: { max: 25_000 } },
  },
  {
    id: "fake-licence", for: ["driver", "papers"],
    title: { en: "No fake, altered or unofficial licences", bn: "জাল, বিকৃত বা অননুমোদিত লাইসেন্স নিষিদ্ধ" },
    detail: {
      en: "Only BRTA may make or renew licences. Using a fake licence, or altering one, is a serious offence.",
      bn: "শুধু কর্তৃপক্ষ লাইসেন্স তৈরি বা নবায়ন করতে পারে। জাল লাইসেন্স ব্যবহার বা লাইসেন্স বিকৃত করা গুরুতর অপরাধ।",
    },
    rule: "10", penalty: "69", p: { jailMonths: { min: 6, max: 24 }, fineBdt: { min: 100_000, max: 500_000 } },
  },
  {
    id: "suspended", for: ["driver", "papers"],
    title: { en: "No driving while the licence is suspended or cancelled", bn: "লাইসেন্স স্থগিত বা বাতিল থাকলে গাড়ি চালানো যাবে না" },
    detail: {
      en: "Once BRTA suspends, withdraws or cancels a licence, its holder may not drive.",
      bn: "কর্তৃপক্ষ লাইসেন্স স্থগিত, প্রত্যাহার বা বাতিল করলে সেই ব্যক্তি গাড়ি চালাতে পারবেন না।",
    },
    rule: "12(3)", penalty: "70", p: { jailMonths: { max: 3 }, fineBdt: { max: 25_000 } },
  },
  {
    id: "conductor", for: ["bus", "papers"],
    title: { en: "Conductors need a conductor licence", bn: "কন্ডাক্টরের লাইসেন্স লাগবে" },
    detail: {
      en: "Nobody may work as a conductor on public transport without a conductor licence.",
      bn: "কন্ডাক্টর লাইসেন্স ছাড়া কেউ গণপরিবহণে কন্ডাক্টরের দায়িত্ব পালন করতে পারবেন না।",
    },
    rule: "14", penalty: "71", p: { jailMonths: { max: 1 }, fineBdt: { max: 5_000 } },
  },
  {
    id: "registration", for: ["driver", "papers"],
    title: { en: "The vehicle must be registered", bn: "গাড়ির রেজিস্ট্রেশন থাকতে হবে" },
    detail: { en: "No driving an unregistered motor vehicle.", bn: "রেজিস্ট্রেশন ছাড়া মোটরযান চালানো যাবে না।" },
    rule: "16", penalty: "72", p: { jailMonths: { max: 6 }, fineBdt: { max: 50_000 } },
  },
  {
    id: "fake-plate", for: ["driver", "papers"],
    title: { en: "No fake registration number or plate", bn: "ভুয়া রেজিস্ট্রেশন নম্বর বা নম্বরপ্লেট নিষিদ্ধ" },
    detail: { en: "Using or showing a false registration number.", bn: "ভুয়া রেজিস্ট্রেশন নম্বর ব্যবহার বা প্রদর্শন।" },
    rule: "17", penalty: "73", p: { jailMonths: { min: 6, max: 24 }, fineBdt: { min: 100_000, max: 500_000 } },
  },
  {
    id: "ownership", for: ["papers"],
    title: { en: "Register a change of owner", bn: "মালিকানা বদল হলে রেজিস্ট্রেশন করতে হবে" },
    detail: { en: "A buyer must register the transfer of a vehicle.", bn: "গাড়ি কেনার পর হস্তান্তরগ্রহীতাকে মালিকানা রেজিস্ট্রেশন করতে হবে।" },
    rule: "21", penalty: "74", p: { jailMonths: { max: 1 }, fineBdt: { max: 5_000 } },
  },
  {
    id: "fitness", for: ["driver", "papers"],
    title: { en: "Valid fitness certificate; no worn-out or unsafe vehicles", bn: "বৈধ ফিটনেস সনদ লাগবে; ঝুঁকিপূর্ণ বা মেয়াদোত্তীর্ণ গাড়ি নয়" },
    detail: {
      en: "No driving without a fitness certificate, with an expired one, or a vehicle past its economic life or unfit and dangerous.",
      bn: "ফিটনেস সনদ ছাড়া, মেয়াদোত্তীর্ণ সনদে, ইকোনমিক লাইফ পেরোনো বা ফিটনেসের অনুপযোগী ঝুঁকিপূর্ণ গাড়ি চালানো যাবে না।",
    },
    rule: "25", penalty: "75", p: { jailMonths: { max: 6 }, fineBdt: { max: 25_000 } },
  },
  {
    id: "tax-token", for: ["driver", "papers"],
    title: { en: "Valid tax token", bn: "বৈধ ট্যাক্স-টোকেন লাগবে" },
    detail: { en: "No driving without a tax token or with an expired one.", bn: "ট্যাক্স-টোকেন ছাড়া বা মেয়াদোত্তীর্ণ টোকেনে গাড়ি চালানো যাবে না।" },
    rule: "26", penalty: "76", p: { fineBdt: { max: 10_000 } },
  },
  {
    id: "route-permit", for: ["bus", "truck", "cng", "papers"],
    title: { en: "Transport vehicles need a route permit", bn: "পরিবহন যানের রুট পারমিট লাগবে" },
    detail: { en: "Buses, trucks, CNGs and other transport vehicles may not run in public places without a route permit.", bn: "রুট পারমিট ছাড়া বাস, ট্রাক, সিএনজি বা অন্য পরিবহন যান পাবলিক প্লেসে চালানো যাবে না।" },
    rule: "28(1)", penalty: "77", p: { jailMonths: { max: 3 }, fineBdt: { max: 20_000 } },
  },
  {
    id: "commercial-use", for: ["car", "cng"],
    title: { en: "No commercial use of a private vehicle without approval", bn: "অনুমতি ছাড়া ব্যক্তিগত গাড়ি বাণিজ্যিকভাবে চালানো যাবে না" },
    detail: {
      en: "A vehicle without a route permit may not be used commercially. Hiring out a private car (for example ride-sharing) needs BRTA's approval under set conditions.",
      bn: "রুট পারমিট নেই এমন গাড়ি বাণিজ্যিক কাজে ব্যবহার করা যাবে না। ব্যক্তিগত গাড়ি ভাড়ায় চালাতে (যেমন রাইড শেয়ার) কর্তৃপক্ষের অনুমতি লাগবে।",
    },
    rule: "31", penalty: "79", p: { jailMonths: { max: 3 }, fineBdt: { max: 25_000 }, points: 1 },
  },
  {
    id: "modification", for: D,
    title: { en: "No illegal changes to the vehicle", bn: "গাড়ির অবৈধ কাঠামোগত পরিবর্তন নিষিদ্ধ" },
    detail: { en: "Breaking BRTA's technical specifications for a vehicle (body, size, fittings).", bn: "কর্তৃপক্ষের নির্ধারিত কারিগরি বিনির্দেশ অমান্য করা।" },
    rule: "40", penalty: "84", p: { jailMonths: { min: 12, max: 36 }, fineBdt: { max: 300_000 } },
  },

  // ------------------------------------------------------------------ driving
  {
    id: "signals", for: ["everyone", "pedestrian", "driver"],
    title: { en: "Obey traffic signs, lights and police signals", bn: "ট্রাফিক সাইন, সিগন্যাল ও পুলিশের সংকেত মানতে হবে" },
    detail: {
      en: "Every driver, pedestrian and road user must follow traffic signs and signals, and stop when a uniformed police officer or vehicle inspector says so. Running a red light also costs demerit points (s.11).",
      bn: "প্রত্যেক চালক, পথচারী ও সড়ক ব্যবহারকারীকে ট্রাফিক সাইন ও সংকেত মানতে হবে এবং পোশাকধারী পুলিশ বা মোটরযান পরিদর্শক থামাতে বললে থামতে হবে। লাল বাতি অমান্য করলে পয়েন্টও কাটা যায় (ধারা ১১)।",
    },
    rule: "42", penalty: "85", p: { jailMonths: { max: 1 }, fineBdt: { max: 10_000 }, points: 1 },
  },
  {
    id: "crossing", for: ["pedestrian", "everyone"],
    title: { en: "Cross only at zebra crossings, foot-bridges or underpasses", bn: "জেব্রা ক্রসিং, ফুটওভার ব্রিজ বা আন্ডারপাস দিয়ে রাস্তা পার হতে হবে" },
    detail: {
      en: "Where a zebra crossing, foot over-bridge or underpass exists, road users must use it to cross.",
      bn: "জেব্রা ক্রসিং, ফুটওভার ব্রিজ, আন্ডারপাস বা এ ধরনের সুবিধা থাকলে সড়ক পারাপারে তা ব্যবহার করতে হবে।",
    },
    rule: "42(3)", penalty: "85", p: { jailMonths: { max: 1 }, fineBdt: { max: 10_000 } },
  },
  {
    id: "overload", for: ["truck", "bus"],
    title: { en: "No overloading (weight or axle limits)", bn: "অনুমোদিত ওজন বা এক্সেল ওজনের বেশি বহন নিষিদ্ধ" },
    detail: {
      en: "No carrying more than the permitted laden, train or axle weight, and no raising the registered unladen weight. Overweight vehicles can also be fined at increasing rates on weighing.",
      bn: "অনুমোদিত লেডেন, ট্রেইন বা এক্সেল ওজনের বেশি বহন করা এবং রেজিস্ট্রেশনের আনলেডেন ওজন বাড়ানো যাবে না। ওজন পরীক্ষায় বাড়তি ওজনের জন্য ক্রমবর্ধমান হারে জরিমানাও হতে পারে।",
    },
    rule: "43", penalty: "86", p: { jailMonths: { max: 12 }, fineBdt: { max: 100_000 }, points: 2 },
  },
  {
    id: "speed", for: D,
    title: { en: "Keep to the speed limit; no reckless driving", bn: "গতিসীমা মানতে হবে; বেপরোয়াভাবে চালানো যাবে না" },
    detail: { en: "No driving above the set speed limit or recklessly.", bn: "নির্ধারিত গতিসীমার বেশি গতিতে বা বেপরোয়াভাবে গাড়ি চালানো যাবে না।" },
    rule: "44(2)", penalty: "87", p: { jailMonths: { max: 3 }, fineBdt: { max: 10_000 }, points: 1 },
  },
  {
    id: "overtaking", for: D,
    title: { en: "No dangerous overtaking or blocking traffic", bn: "বিপজ্জনক ওভারটেকিং বা চলাচলে বাধা নিষিদ্ধ" },
    detail: {
      en: "No dangerous or unauthorised overtaking, and no obstructing other vehicles. Overtaking at or near a pedestrian crossing also costs demerit points (s.11).",
      bn: "বিপজ্জনকভাবে বা অননুমোদিতভাবে ওভারটেকিং এবং অন্য গাড়ির চলাচলে বাধা সৃষ্টি করা যাবে না। পথচারী পারাপারের স্থানে বা কাছে ওভারটেক করলে পয়েন্ট কাটা যায় (ধারা ১১)।",
    },
    rule: "44(3)", penalty: "87", p: { jailMonths: { max: 3 }, fineBdt: { max: 10_000 }, points: 1 },
  },
  {
    id: "horn", for: D,
    title: { en: "No loud horns: silent zones, noise limits, hydraulic horns", bn: "উচ্চ শব্দ নিষিদ্ধ: নীরব এলাকা, শব্দসীমা, হাইড্রোলিক হর্ন" },
    detail: {
      en: "No noise above the set limit, no horn at all in a declared silent zone (around hospitals, schools and the like), and no fitting or using horns or devices louder than allowed. Ambulances and fire engines are exempt.",
      bn: "নির্ধারিত শব্দমাত্রার বেশি শব্দ, ঘোষিত নীরব এলাকায় যেকোনো হর্ন, এবং অনুমোদিত মাত্রার বেশি শব্দের হর্ন বা যন্ত্র লাগানো বা ব্যবহার করা যাবে না। অ্যাম্বুলেন্স ও অগ্নি-নির্বাপক যান ব্যতিক্রম।",
    },
    rule: "45", penalty: "88", p: { jailMonths: { max: 3 }, fineBdt: { max: 10_000 }, points: 1 },
  },
  {
    id: "pollution", for: D,
    title: { en: "No polluting or dangerous vehicles", bn: "পরিবেশ দূষণকারী বা ঝুঁকিপূর্ণ গাড়ি চালানো নিষিদ্ধ" },
    detail: {
      en: "No driving a vehicle whose smoke or other emissions exceed the government limit, and no fitting or using polluting devices or parts.",
      bn: "সরকার নির্ধারিত মাত্রার অতিরিক্ত পরিবেশ দূষণকারী ধোঁয়া বা নিঃসরণ হয় এমন গাড়ি চালানো এবং দূষণকারী যন্ত্র বা যন্ত্রাংশ লাগানো বা ব্যবহার করা যাবে না।",
    },
    rule: "46(2)-(3)", penalty: "89(1)", p: { jailMonths: { max: 3 }, fineBdt: { max: 25_000 }, points: 1 },
  },
  {
    id: "unfit-vehicles", for: ["cng", "everyone"],
    title: { en: "No easy-bikes, battery rickshaws, nasimon or karimon on roads and highways", bn: "সড়ক-মহাসড়কে ইজি-বাইক, ব্যাটারিচালিত রিকশা, নসিমন-করিমন নিষিদ্ধ" },
    detail: {
      en: "No driving, or letting anyone drive, a faulty, dangerous, banned or restricted vehicle, or one unfit for roads and highways. The act names nasimon, karimon, bhot-bhoti, easy-bikes, motorised rickshaws or vans and similar three-wheelers, plus any vehicle the government or BRTA bans.",
      bn: "ত্রুটিপূর্ণ, ঝুঁকিপূর্ণ, নিষিদ্ধ বা বিধি-নিষেধ আরোপকৃত বা সড়ক-মহাসড়কে চলাচলের অনুপযোগী গাড়ি চালানো বা চালাতে দেওয়া যাবে না। আইনে নসিমন, করিমন, ভটভটি, ইজি-বাইক, মোটরচালিত রিকশা বা ভ্যান ও অনুরূপ থ্রি-হুইলারের কথা বলা আছে।",
    },
    rule: "46(4)", penalty: "89(2)", p: { jailMonths: { max: 3 }, fineBdt: { max: 20_000 }, points: 1 },
  },
  {
    id: "parking", for: ["driver", "bus"], detects: true,
    title: { en: "Park and stop only where allowed (buses: only at bus stops)", bn: "শুধু নির্ধারিত স্থানে পার্কিং ও থামানো (বাস শুধু স্টপেজে)" },
    detail: {
      en: "Park only in designated parking areas, and stop to pick up or drop off passengers or goods only at the designated places and times. Passengers may not ask or force a driver to stop elsewhere. A bus stopping mid-road to pick up passengers breaks this rule.",
      bn: "নির্ধারিত পার্কিং এলাকা ছাড়া পার্কিং করা যাবে না এবং যাত্রী বা পণ্য ওঠানামার নির্ধারিত স্থান ও সময় ছাড়া গাড়ি থামানো যাবে না। যাত্রীরাও অন্য জায়গায় থামাতে অনুরোধ বা বাধ্য করতে পারবেন না। রাস্তার মাঝে বাস থামিয়ে যাত্রী তোলা এই নিয়মের লঙ্ঘন।",
    },
    rule: "47", penalty: "90", p: { fineBdt: { max: 5_000 }, points: 1 },
  },
  {
    id: "highway-entry", for: D,
    title: { en: "Give way to highway traffic when joining", bn: "মহাসড়কে প্রবেশের সময় মহাসড়কের গাড়িকে অগ্রাধিকার দিতে হবে" },
    detail: {
      en: "Vehicles entering a highway must give priority to traffic already on it. Between two highways, the busier one has priority.",
      bn: "মহাসড়কে প্রবেশের সময় মহাসড়কে চলমান গাড়ি অগ্রাধিকার পাবে। এক মহাসড়ক থেকে অন্যটিতে প্রবেশে যেটিতে গাড়ি বেশি, সেটি অগ্রাধিকার পাবে।",
    },
    rule: "48", penalty: "91", p: { jailMonths: { max: 1 }, fineBdt: { max: 5_000 }, points: 1 },
  },

  // s.49(1) first part → s.92(1): up to 3 months and/or Tk 10,000, 1 point
  {
    id: "drunk", for: D,
    title: { en: "No drink or drug driving", bn: "মদ্যপান বা নেশা করে গাড়ি চালানো নিষিদ্ধ" },
    detail: {
      en: "No driving after alcohol or drugs. Conductors and workers may not be on the vehicle intoxicated either.",
      bn: "মদ্যপান বা নেশাজাতীয় দ্রব্য সেবন করে গাড়ি চালানো যাবে না; কন্ডাক্টর বা শ্রমিকও নেশাগ্রস্ত অবস্থায় গাড়িতে থাকতে পারবেন না।",
    },
    rule: "49(1) ক-খ", penalty: "92(1)", p: { jailMonths: { max: 3 }, fineBdt: { max: 10_000 }, points: 1 },
  },
  {
    id: "helper-driving", for: ["bus", "truck"],
    title: { en: "Never hand the wheel to the conductor or helper", bn: "কন্ডাক্টর বা হেলপারকে দিয়ে গাড়ি চালানো যাবে না" },
    detail: { en: "A driver may not, in any situation, let the conductor or a worker drive.", bn: "চালক কোনো অবস্থাতেই কন্ডাক্টর বা মোটরযান শ্রমিককে গাড়ি চালানোর দায়িত্ব দিতে পারবেন না।" },
    rule: "49(1) গ", penalty: "92(1)", p: { jailMonths: { max: 3 }, fineBdt: { max: 10_000 }, points: 1 },
  },
  {
    id: "wrong-way", for: D, detects: true,
    title: { en: "No wrong-way driving", bn: "উল্টো পথে গাড়ি চালানো নিষিদ্ধ" },
    detail: {
      en: "No driving against the set direction on a road or highway. On a one-way road it also costs demerit points (s.11).",
      bn: "সড়ক বা মহাসড়কে নির্ধারিত অভিমুখের বিপরীত দিক থেকে গাড়ি চালানো যাবে না। একমুখী সড়কে উল্টো দিকে চালালে পয়েন্টও কাটা যায় (ধারা ১১)।",
    },
    rule: "49(1) ঘ", penalty: "92(1)", p: { jailMonths: { max: 3 }, fineBdt: { max: 10_000 }, points: 1 },
  },
  {
    id: "obstruct-stop", for: D, detects: true,
    title: { en: "No stopping in the road, on the wrong side, or blocking traffic", bn: "রাস্তায়, উল্টো পাশে থামিয়ে যানজট বা বাধা সৃষ্টি নিষিদ্ধ" },
    detail: {
      en: "No stopping anywhere except the set places, or on the wrong side, in a way that causes a jam or another obstruction.",
      bn: "নির্ধারিত স্থান ছাড়া অন্য কোথাও বা উল্টো পাশে বা ভুল দিকে (wrong side) গাড়ি থামিয়ে যানজট বা অন্য কোনো প্রতিবন্ধকতা সৃষ্টি করা যাবে না।",
    },
    rule: "49(1) ঙ", penalty: "92(1)", p: { jailMonths: { max: 3 }, fineBdt: { max: 10_000 }, points: 1 },
  },
  {
    id: "helmet", for: ["motorcycle"],
    title: { en: "Helmets for rider and passenger; at most one passenger", bn: "চালক ও আরোহী দুজনেরই হেলমেট; একজনের বেশি আরোহী নয়" },
    detail: {
      en: "A motorcycle may carry no more than one passenger besides the rider, and both must wear a helmet properly.",
      bn: "চালক ছাড়া মোটরসাইকেলে একজনের বেশি সহযাত্রী বহন করা যাবে না এবং চালক ও সহযাত্রী উভয়কে যথাযথভাবে হেলমেট পরতে হবে।",
    },
    rule: "49(1) চ", penalty: "92(1)", p: { jailMonths: { max: 3 }, fineBdt: { max: 10_000 }, points: 1 },
  },
  {
    id: "moving-boarding", for: ["bus", "cng"],
    title: { en: "No picking up or dropping passengers while moving", bn: "চলন্ত অবস্থায় যাত্রী ওঠানো-নামানো নিষিদ্ধ" },
    detail: { en: "Nobody may let passengers on or off a moving vehicle.", bn: "চলন্ত অবস্থায় চালক, কন্ডাক্টর বা অন্য কেউ যাত্রী ওঠাতে বা নামাতে পারবেন না।" },
    rule: "49(1) ছ", penalty: "92(1)", p: { jailMonths: { max: 3 }, fineBdt: { max: 10_000 }, points: 1 },
  },
  {
    id: "disabled-access", for: ["bus"],
    title: { en: "Facilities for passengers with disabilities", bn: "প্রতিবন্ধী যাত্রীদের জন্য সুবিধা রাখতে হবে" },
    detail: { en: "Public transport must have suitable facilities for passengers with disabilities.", bn: "গণপরিবহণে প্রতিবন্ধী যাত্রীদের জন্য অনুকূল সুযোগ-সুবিধা রাখতে হবে।" },
    rule: "49(1) জ", penalty: "92(1)", p: { jailMonths: { max: 3 }, fineBdt: { max: 10_000 } },
  },
  {
    id: "roof-riding", for: ["bus", "truck", "cng"],
    title: { en: "No passengers or goods on the roof or outside the body", bn: "ছাদে বা বডির বাইরে যাত্রী বা মালামাল নিষিদ্ধ" },
    detail: { en: "No carrying passengers, goods or luggage on the front, back, sides, outside the body or on the roof.", bn: "গাড়ির সামনে, পিছনে, দুই পাশে, বডির বাইরে বা ছাদে কোনো যাত্রী, পণ্য বা মালামাল বহন করা যাবে না।" },
    rule: "49(1) ঝ", penalty: "92(1)", p: { jailMonths: { max: 3 }, fineBdt: { max: 10_000 }, points: 1 },
  },
  {
    id: "ads", for: D,
    title: { en: "No advertising on vehicles without approval", bn: "অনুমতি ছাড়া গাড়িতে বিজ্ঞাপন নিষিদ্ধ" },
    detail: { en: "No advertisements on a vehicle without approval from the government or BRTA.", bn: "সরকার বা কর্তৃপক্ষের অনুমোদন ছাড়া গাড়িতে বিজ্ঞাপন প্রদর্শন বা প্রচার করা যাবে না।" },
    rule: "49(1) ঞ", penalty: "92(1)", p: { jailMonths: { max: 3 }, fineBdt: { max: 10_000 } },
  },
  {
    id: "road-blocking", for: ["everyone"],
    title: { en: "No shops, repairs or goods blocking roads and footpaths", bn: "রাস্তা বা ফুটপাতে দোকান, মেরামত বা মালামাল রেখে বাধা সৃষ্টি নিষিদ্ধ" },
    detail: {
      en: "No blocking a highway, road, footpath, overpass or underpass with parts, goods, roadside repairs or shops.",
      bn: "মহাসড়ক, সড়ক, ফুটপাত, ওভারপাস বা আন্ডারপাসে মেরামতের নামে যন্ত্রাংশ বা মালামাল রেখে বা দোকান বসিয়ে যানবাহন বা পথচারী চলাচলে বাধা সৃষ্টি করা যাবে না।",
    },
    rule: "49(1) ট", penalty: "92(1)", p: { jailMonths: { max: 3 }, fineBdt: { max: 10_000 } },
  },
  {
    id: "footpath", for: ["driver", "motorcycle"],
    title: { en: "No driving on the footpath", bn: "ফুটপাত দিয়ে গাড়ি চালানো নিষিদ্ধ" },
    detail: { en: "No motor vehicle may use the footpath beside a road (a common motorcycle offence in jams).", bn: "সড়কের পাশের ফুটপাতের উপর দিয়ে কোনো মোটরযান চলতে পারবে না (যানজটে মোটরসাইকেলের সাধারণ অপরাধ)।" },
    rule: "49(1) ঠ", penalty: "92(1)", p: { jailMonths: { max: 3 }, fineBdt: { max: 10_000 }, points: 1 },
  },
  {
    id: "joyride", for: ["everyone"],
    title: { en: "No taking a vehicle without the owner's permission", bn: "মালিকের অনুমতি ছাড়া গাড়ি চালিয়ে নিয়ে যাওয়া নিষিদ্ধ" },
    detail: {
      en: "Nobody may drive a vehicle away without permission from its owner or a lawful authority, or get into a parked vehicle without a reason.",
      bn: "মালিক বা আইনানুগ কর্তৃপক্ষের অনুমতি ছাড়া কেউ গাড়ি চালিয়ে নিয়ে যেতে পারবেন না, এবং যুক্তিসঙ্গত কারণ ছাড়া দাঁড়িয়ে থাকা গাড়িতে ঢুকতে পারবেন না।",
    },
    rule: "49(1) ড-ঢ", penalty: "92(1)", p: { jailMonths: { max: 3 }, fineBdt: { max: 10_000 } },
  },

  // s.49(1) second part → s.92(2): up to 1 month and/or Tk 5,000, 1 point
  {
    id: "phone", for: D,
    title: { en: "No mobile phone while driving", bn: "গাড়ি চালানোর সময় মোবাইল ফোন নিষিদ্ধ" },
    detail: { en: "No using a mobile phone or similar device while driving.", bn: "চালনারত অবস্থায় চালক মোবাইল ফোন বা অনুরূপ সরঞ্জাম ব্যবহার করতে পারবেন না।" },
    rule: "49(1) ২য় অংশ ক", penalty: "92(2)", p: { jailMonths: { max: 1 }, fineBdt: { max: 5_000 }, points: 1 },
  },
  {
    id: "seatbelt", for: ["car", "bus", "truck"],
    title: { en: "Wear a seat belt", bn: "সিটবেল্ট বাঁধতে হবে" },
    detail: { en: "Drivers must wear a seat belt. Passengers must follow the seat-belt rules made under the act.", bn: "চালককে সিটবেল্ট বেঁধে গাড়ি চালাতে হবে; যাত্রীদের সিটবেল্ট সংক্রান্ত নির্ধারিত বিধান মানতে হবে।" },
    rule: "49(1) ২য় অংশ খ, ঙ", penalty: "92(2)", p: { jailMonths: { max: 1 }, fineBdt: { max: 5_000 }, points: 1 },
  },
  {
    id: "distract", for: ["everyone"],
    title: { en: "Passengers: don't distract the driver", bn: "যাত্রী: চালকের মনোযোগে ব্যাঘাত ঘটানো যাবে না" },
    detail: { en: "Passengers may not do anything in a moving vehicle that distracts the driver or makes driving difficult.", bn: "চলন্ত গাড়িতে যাত্রী এমন কিছু করতে পারবেন না যাতে চালকের মনোসংযোগে ব্যাঘাত ঘটে বা চালাতে অসুবিধা হয়।" },
    rule: "49(1) ২য় অংশ গ", penalty: "92(2)", p: { jailMonths: { max: 1 }, fineBdt: { max: 5_000 } },
  },
  {
    id: "reserved-seats", for: ["bus", "everyone"],
    title: { en: "Keep reserved seats free", bn: "সংরক্ষিত আসনে বসা যাবে না" },
    detail: { en: "Other passengers may not sit in seats reserved for women, children, people with disabilities and older passengers.", bn: "মহিলা, শিশু, প্রতিবন্ধী ও বয়োজ্যেষ্ঠ যাত্রীদের সংরক্ষিত আসনে অন্য যাত্রী বসবেন না।" },
    rule: "49(1) ২য় অংশ ঘ", penalty: "92(2)", p: { jailMonths: { max: 1 }, fineBdt: { max: 5_000 } },
  },
  {
    id: "overcrowding", for: ["bus"],
    title: { en: "Long-distance: no more passengers than allowed", bn: "দূরপাল্লায় নির্ধারিত সংখ্যার বেশি যাত্রী নিষিদ্ধ" },
    detail: { en: "Long-distance vehicles may not carry more than their set number of passengers.", bn: "দূরপাল্লার গাড়িতে নির্ধারিত সংখ্যার বেশি যাত্রী বা আরোহী বহন করা যাবে না।" },
    rule: "49(1) ২য় অংশ চ", penalty: "92(2)", p: { jailMonths: { max: 1 }, fineBdt: { max: 5_000 }, points: 1 },
  },
  {
    id: "harassment", for: ["bus", "cng"],
    title: { en: "No misbehaving with or harassing passengers", bn: "যাত্রীদের সঙ্গে দুর্ব্যবহার বা হয়রানি নিষিদ্ধ" },
    detail: { en: "Drivers, conductors and staff may not misbehave with, be rude to or harass passengers.", bn: "চালক, কন্ডাক্টর বা সংশ্লিষ্ট কেউ যাত্রীদের সঙ্গে দুর্ব্যবহার, অসৌজন্যমূলক আচরণ বা হয়রানি করতে পারবেন না।" },
    rule: "49(1) ২য় অংশ ছ", penalty: "92(2)", p: { jailMonths: { max: 1 }, fineBdt: { max: 5_000 }, points: 1 },
  },
  {
    id: "high-beam", for: D,
    title: { en: "No dazzling high beam at night", bn: "রাতে বিপরীত দিকের চালককে বিঘ্নকারী হাইবিম নিষিদ্ধ" },
    detail: { en: "At night, no driving on high beam where it dazzles oncoming drivers.", bn: "রাতে বিপরীত দিক থেকে আসা গাড়ির চালনায় বিঘ্ন ঘটায় এমন হাইবিম ব্যবহার করা যাবে না।" },
    rule: "49(1) ২য় অংশ জ", penalty: "92(2)", p: { jailMonths: { max: 1 }, fineBdt: { max: 5_000 }, points: 1 },
  },

  // ------------------------------------------------------------------ fares, goods
  {
    id: "fare-chart", for: ["bus"],
    title: { en: "Show the fare chart; never charge more than the set fare", bn: "ভাড়ার চার্ট প্রদর্শন; নির্ধারিত ভাড়ার বেশি নেওয়া যাবে না" },
    detail: { en: "Public transport must display the fare chart and may not demand or collect more than the set fare.", bn: "গণপরিবহণে ভাড়ার চার্ট প্রদর্শন করতে হবে এবং নির্ধারিত ভাড়ার বেশি দাবি বা আদায় করা যাবে না।" },
    rule: "34(3)-(4)", penalty: "80", p: { jailMonths: { max: 1 }, fineBdt: { max: 10_000 }, points: 1 },
  },
  {
    id: "meter", for: ["cng"],
    title: { en: "CNG / taxi: no meter tampering or overcharging", bn: "সিএনজি/ট্যাক্সি: মিটার টেম্পারিং বা বাড়তি ভাড়া নিষিদ্ধ" },
    detail: { en: "Contract carriages (CNG auto-rickshaws, taxis) may not illegally alter the meter or demand more than the fare.", bn: "কনট্রাক্ট ক্যারিজের (সিএনজি অটোরিকশা, ট্যাক্সি) মিটার অবৈধভাবে পরিবর্তন বা অতিরিক্ত ভাড়া দাবি বা আদায় করা যাবে না।" },
    rule: "35", penalty: "81", p: { jailMonths: { max: 6 }, fineBdt: { max: 50_000 }, points: 1 },
  },
  {
    id: "explosives", for: ["truck", "bus"],
    title: { en: "Explosives and flammable goods only with approved packing and vehicles", bn: "বিস্ফোরক বা দাহ্য পদার্থ শুধু অনুমোদিত প্যাকিং ও গাড়িতে" },
    detail: { en: "Explosive or flammable goods may only be carried with approved packing and special precautions, in a suitable special vehicle and at the set times.", bn: "অনুমোদিত প্যাকিং ও বিশেষ সতর্কতা, উপযুক্ত বিশেষ ধরনের গাড়ি এবং নির্ধারিত সময় ছাড়া বিস্ফোরক বা দাহ্য পদার্থ পরিবহন করা যাবে না।" },
    rule: "51", penalty: "93", p: { jailMonths: { max: 3 }, fineBdt: { max: 25_000 } },
  },

  // ------------------------------------------------------------------ accidents & behaviour
  {
    id: "injured", for: ["driver", "bus"],
    title: { en: "After a crash: tell the police and get the injured to hospital", bn: "দুর্ঘটনার পর থানায় জানানো ও আহতকে হাসপাতালে পাঠানো" },
    detail: {
      en: "After a road accident the driver, conductor or their representative must at once inform the nearest police station (and fire service or hospital as needed), and send injured people for treatment as fast as possible.",
      bn: "সড়ক দুর্ঘটনা ঘটলে চালক, কন্ডাক্টর বা তাদের প্রতিনিধিকে তাৎক্ষণিকভাবে নিকটস্থ থানা এবং প্রয়োজনে ফায়ার সার্ভিস বা হাসপাতালকে জানাতে হবে এবং আহতকে দ্রুততম সময়ে চিকিৎসার জন্য পাঠাতে হবে।",
    },
    rule: "62(1)", penalty: "95", p: { jailMonths: { max: 1 }, fineBdt: { max: 20_000 }, points: 1 },
  },
  {
    id: "crash-damage", for: D,
    title: { en: "Crash caused by speeding, recklessness, overtaking or overloading", bn: "অতিরিক্ত গতি, বেপরোয়া চালনা, ওভারটেকিং বা ওভারলোডিংয়ে দুর্ঘটনা" },
    detail: {
      en: "If speeding, reckless driving, dangerous overtaking, overloading or loss of control causes a crash with loss of life or property, the driver, conductor or helper is punished. The court may order the fine paid to the victim.",
      bn: "অতিরিক্ত গতি, বেপরোয়া চালনা, ঝুঁকিপূর্ণ ওভারটেকিং, ওভারলোডিং বা নিয়ন্ত্রণহীন চালনায় দুর্ঘটনায় জীবন ও সম্পত্তির ক্ষতি হলে চালক, কন্ডাক্টর বা সহায়তাকারী দণ্ডিত হবেন; আদালত জরিমানার অর্থ ক্ষতিগ্রস্তকে দিতে বলতে পারেন।",
    },
    rule: "98", penalty: "98", p: { jailMonths: { max: 36 }, fineBdt: { max: 300_000 } },
  },
  {
    id: "crash-death", for: D,
    title: { en: "Serious injury or death from reckless or negligent driving", bn: "বেপরোয়া বা অবহেলায় চালনায় গুরুতর আহত বা মৃত্যু" },
    detail: {
      en: "Serious injury or death in a crash is dealt with under the Penal Code. Where it is caused by reckless or negligent driving, the act sets the punishment.",
      bn: "দুর্ঘটনায় গুরুতর আহত বা প্রাণহানি দণ্ডবিধি অনুযায়ী অপরাধ। বেপরোয়া বা অবহেলাজনিত চালনায় ঘটলে এই আইনে দণ্ড নির্ধারিত।",
    },
    rule: "105", penalty: "105", p: { jailMonths: { max: 60 }, fineBdt: { max: 500_000 } },
  },
  {
    id: "aggression", for: ["everyone"],
    title: { en: "After a crash: no attacking the vehicle, driver or passengers", bn: "দুর্ঘটনার পর গাড়ি, চালক বা যাত্রীর উপর হামলা নিষিদ্ধ" },
    detail: {
      en: "Nobody may damage a vehicle involved in an accident or attack its driver or conductor. Passengers and onlookers may not act aggressively, and no group may damage vehicles or attack passengers under an organisation's banner.",
      bn: "দুর্ঘটনা কবলিত গাড়ির ক্ষতি করা বা চালক-কন্ডাক্টরের প্রতি আক্রমণাত্মক আচরণ করা যাবে না; যাত্রী বা সমবেত লোকজন জনশৃঙ্খলা বিরোধী আচরণ করতে পারবেন না; কোনো সংগঠনের ব্যানারে গাড়ির ক্ষতি বা যাত্রীর উপর আক্রমণ করা যাবে না।",
    },
    rule: "119", penalty: "103", p: { jailMonths: { max: 1 }, fineBdt: { max: 10_000 } },
  },
  {
    id: "inspection", for: ["everyone", "papers"],
    title: { en: "Don't obstruct inspections; follow official orders", bn: "পরিদর্শনে বাধা দেওয়া বা নির্দেশ অমান্য নিষিদ্ধ" },
    detail: { en: "Obstructing an inspection or ignoring its directions (s.116(2)), and refusing to obey orders or give information (s.118), are offences.", bn: "পরিদর্শনে বাধা বা নির্দেশনা অমান্য (ধারা ১১৬(২)) এবং আদেশ পালন ও তথ্য প্রদানে অস্বীকৃতি (ধারা ১১৮) অপরাধ।" },
    rule: "116, 118", penalty: "101, 102", p: { jailMonths: { max: 1 }, fineBdt: { max: 10_000 } },
  },
];

export const CATS: Cat[] = ["everyone", "pedestrian", "car", "motorcycle", "bus", "truck", "cng", "papers"];
const DRIVER_CATS: Cat[] = ["car", "motorcycle", "bus", "truck", "cng"];

export function rulesFor(cat: Cat | "all"): Rule[] {
  if (cat === "all") return RULES;
  return RULES.filter((r) => r.for.includes(cat) || (r.for.includes("driver") && DRIVER_CATS.includes(cat)));
}

export const SOURCE_URL = "http://bdlaws.minlaw.gov.bd/act-details-1262.html";
export const CHECKED = "2026-11-05";
