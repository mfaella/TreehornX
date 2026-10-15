struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_unsafe_insert(struct Node *root) {
    int key;
    struct Node *z;
    struct Node *x;
    struct Node *w;
    int xkey;
    int wkey;

    z = malloc(sizeof(struct Node));
    z->data = key;

    x = root;

    if (x != NULL) {//3
        xkey = x->data; //4
        if (xkey <= key) { //5
            w = x->right; //6
        }
        else {
            w = x->left; //7
        }
        while(w != NULL) { //8
            wkey = w->data;
            x = w;
            if(wkey <= key) { //11
                w = w->right;
            }
            else {
                w = w->left; //13
            }
        }
        x = w; // 14 //error
        xkey = x->data; //15
        if (xkey <= key) {
            x->right = z;
        } 
        else {
            x->left = z;
        }
    }
}
