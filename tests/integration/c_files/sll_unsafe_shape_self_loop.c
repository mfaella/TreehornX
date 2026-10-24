// the head points to itself
struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_shape_self_loop(struct Node *root) {

    if (!root) {
        return;
    }
    root->next = root;
}
