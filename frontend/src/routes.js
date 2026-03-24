import HomePage from "./views/HomePage.vue";
import CallbackPage from "./views/CallbackPage.vue";
import BookshelfPage from "./views/BookshelfPage.vue";
import StoryResultPage from "./views/StoryResultPage.vue";
import StoryHistoryPage from "./views/StoryHistoryPage.vue";

export const routes = [
  { path: "/", component: HomePage },
  { path: "/api/auth/callback", component: CallbackPage },
  { path: "/bookshelf", component: BookshelfPage },
  { path: "/story/result", component: StoryResultPage },
  { path: "/stories", component: StoryHistoryPage }
];
